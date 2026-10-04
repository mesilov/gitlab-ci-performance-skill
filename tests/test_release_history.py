import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_ci_report import ci, sample


def releases():
    s = sample()
    for p, j in zip(s["pipelines"], s["jobs"]):
        p["ref"] = j["ref"] = "v1." + str(p["id"])
        p["sha"] = str(p["id"])
        j["runner"] = {"id": p["id"], "description": "runner"}
    return s


class ReleaseHistoryTests(unittest.TestCase):
    def history(self, snapshot=None, refs=None):
        snapshot = snapshot or releases()
        return ci.build_report(snapshot, release_refs=refs or [p["ref"] for p in snapshot["pipelines"]])["release_history"]

    def test_unique_tags_have_history_and_default_stays_same_ref(self):
        s = releases()
        default = ci.build_report(s)
        self.assertIn("release_history", default)
        self.assertIsNone(default["release_history"])
        self.assertTrue(all(v["insufficient_count"] for v in default["views"]))
        report = ci.build_report(s, release_refs=["v1.4", "v1.1", "v1.3", "v1.2"])
        self.assertEqual(report["views"], default["views"])
        h = report["release_history"]
        self.assertEqual(h["refs"], ["v1.1", "v1.2", "v1.3", "v1.4"])
        g = h["groups"][0]
        self.assertEqual(g["attempt_ids"], [1, 2, 3, 4])
        self.assertEqual(g["current_period"]["pipeline_ids"], [4])
        self.assertEqual(g["baseline_period"]["pipeline_ids"], [3, 2, 1])
        self.assertEqual(g["execution_change"]["status"], "observed_increase")
        self.assertEqual(g["execution_change"]["delta_seconds"], 50)
        self.assertEqual(g["queue_change"]["delta_seconds"], 45)
        self.assertEqual(g["baseline"]["execution"]["known"], 3)
        self.assertIn("different_refs", g["context"]["differences"])
        self.assertIn("different_runners", g["context"]["differences"])
        self.assertIn("configuration_not_verified", g["context"]["limitations"])

    def test_selection_is_exact_and_invalid_refs_rejected(self):
        for refs in [["v1.*"], ["missing"], ["v1.1", "v1.1"], []]:
            with self.assertRaises(ValueError):
                ci.build_report(releases(), release_refs=refs)
        h = self.history(refs=["v1.1", "v1.4"])
        self.assertEqual(h["groups"][0]["attempt_ids"], [1, 4])
        self.assertEqual(h["groups"][0]["execution_change"]["status"], "insufficient_data")

    def test_failed_rerun_missing_and_zero_measurements(self):
        s = releases()
        failed = copy.deepcopy(s["jobs"][-1])
        failed.update(id=5, status="failed", duration_seconds=999)
        s["jobs"].append(failed)
        s["jobs"][-2]["queued_seconds"] = None
        for j in s["jobs"][:3]:
            j["duration_seconds"] = 0
        g = self.history(s)["groups"][0]
        self.assertEqual(g["attempt_ids"], [1, 2, 3, 4, 5])
        self.assertEqual(g["current"]["rerun_attempts"], 1)
        self.assertEqual(g["current"]["execution"]["p50_seconds"], 150)
        self.assertEqual(g["current"]["queue"]["missing"], 1)
        self.assertIsNone(g["queue_change"]["delta_seconds"])
        self.assertIsNone(g["execution_change"]["delta_percent"])
        self.assertEqual(g["execution_change"]["status"], "observed_increase")

    def test_stage_and_unsuccessful_pipeline_are_not_mixed(self):
        s = releases()
        s["pipelines"][-1]["status"] = "failed"
        s["jobs"][-1]["stage"] = "other"
        h = self.history(s)
        self.assertEqual(len(h["groups"]), 2)
        other = next(g for g in h["groups"] if g["stage"] == "other")
        self.assertEqual(other["attempt_ids"], [4])
        self.assertEqual(other["current_period"]["pipeline_ids"], [])
        self.assertEqual(other["execution_change"]["status"], "insufficient_data")

    def test_order_uses_pipeline_creation_time_and_context_is_preserved(self):
        s = releases()
        s["pipelines"][0]["created_at"] = "2026-10-03T00:00:00Z"
        s["pipelines"][0]["source"] = "web"
        g = self.history(s)["groups"][0]
        self.assertEqual(g["attempt_ids"], [2, 3, 4, 1])
        self.assertEqual(g["current_period"]["pipeline_ids"], [1])
        self.assertIn("different_pipeline_sources", g["context"]["differences"])
        self.assertEqual(g["context"]["current"]["pipeline_sources"], ["web"])
        self.assertEqual(g["context"]["current"]["shas"], ["1"])

    def test_report_contract_version_and_legacy_render(self):
        report = ci.build_report(releases())
        self.assertEqual(report["schema_version"], "1.1.0")
        self.assertEqual(report["calculation_version"], "1.1.0")
        legacy = ci.load(ci.ROOT.parents[1] / "examples/report.json")
        ci.validate(legacy, "report")
        with tempfile.TemporaryDirectory() as d:
            ci.render(legacy, Path(d)/"legacy.html")
        bad = copy.deepcopy(report)
        del bad["release_history"]
        with self.assertRaises(ValueError):
            ci.validate(bad, "report")

    def test_cli_accepts_explicit_release_refs(self):
        with tempfile.TemporaryDirectory() as d:
            snapshot = Path(d)/"jobs.json"
            output = Path(d)/"report.json"
            ci.save(snapshot, releases(), "jobs")
            with patch("sys.argv", ["ci_report.py", "report", "--snapshot", str(snapshot),
                                    "--release-refs", "v1.1", "v1.2", "v1.3", "v1.4", "--output", str(output)]):
                ci.main()
            self.assertEqual(ci.load(output)["release_history"]["groups"][0]["attempt_ids"], [1, 2, 3, 4])


class ReleaseContractTests(unittest.TestCase):
    def test_attempt_ids_and_derived_values_must_match_source(self):
        for field, value in [("attempt_ids", [999]), ("current_attempt_ids", [1]),
                             ("baseline_attempt_ids", [4])]:
            report = ci.build_report(releases(), release_refs=["v1.1", "v1.2", "v1.3", "v1.4"])
            report["release_history"]["groups"][0][field] = value
            with self.assertRaises(ValueError):
                ci.validate(report, "report")
        report = ci.build_report(releases(), release_refs=["v1.1", "v1.2", "v1.3", "v1.4"])
        report["release_history"]["groups"][0]["execution_change"]["delta_seconds"] = 999
        with self.assertRaises(ValueError):
            ci.validate(report, "report")

    def test_reruns_cannot_supply_three_independent_baseline_pipelines(self):
        s = releases()
        s["jobs"] = [s["jobs"][0], s["jobs"][-1]]
        for i in [5, 6]:
            s["jobs"].append({**s["jobs"][0], "id": i})
        g = ci.build_report(s, release_refs=["v1.1", "v1.4"])["release_history"]["groups"][0]
        self.assertEqual(g["baseline"]["execution"]["known"], 3)
        self.assertEqual(g["execution_change"]["status"], "insufficient_data")

    def test_selection_and_report_do_not_mutate_snapshot_or_merge_external_baseline(self):
        s = releases()
        original = copy.deepcopy(s)
        baseline = copy.deepcopy(s)
        baseline["collected_at"] = "2026-10-03T00:00:00Z"
        baseline["jobs"][0]["duration_seconds"] = 500
        refs = [p["ref"] for p in s["pipelines"]]
        report = ci.build_report(s, release_refs=refs)
        other = ci.build_report(s, baseline=baseline, release_refs=refs)
        self.assertEqual(s, original)
        self.assertEqual(report["release_history"], other["release_history"])
        self.assertEqual(report["inputs"]["snapshot_sha256"], ci.digest(s))
