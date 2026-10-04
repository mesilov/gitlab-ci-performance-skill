"""Synthetic trace evidence regressions; raw private logs are never fixtures."""
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/gitlab-ci-performance/scripts"
sys.path.insert(0, str(SCRIPTS))
if importlib.util.find_spec("trace_parser"):
    from trace_parser import parse_trace
else:
    parse_trace = None


class TraceParserTests(unittest.TestCase):
    def parse(self, text, **kwargs):
        self.assertIsNotNone(parse_trace, "pure trace parser is not implemented")
        return parse_trace(text.encode(), {"id": 123, "started_at": "2026-10-04T00:00:00Z"},
                           "2026-10-04T01:00:00Z", **kwargs)

    def test_section_duration_positions_and_source_hash(self):
        raw = "\x1b[0Ksection_start:1791072002:prepare_executor[collapsed=true]\r\x1b[0KPRIVATE\nsection_end:1791072007:prepare_executor\r\x1b[0K\n"
        result = self.parse(raw)
        phase = result["phases"][0]
        self.assertEqual((phase["duration_seconds"], phase["start_seconds"], phase["end_seconds"]), (5, 2, 7))
        self.assertEqual((phase["label"], phase["category"]), ("prepare_executor", "runner_prepare"))
        self.assertEqual((phase["first_line"], phase["last_line"]), (1, 2))
        self.assertEqual(phase["timing_source"], "runner_section")
        self.assertEqual(phase["position_source"], "section_markers")
        self.assertEqual(result["trace_sha256"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(result["trace_bytes"], len(raw.encode()))
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_partial_section_and_missing_job_origin(self):
        self.assertIsNotNone(parse_trace, "pure trace parser is not implemented")
        result = parse_trace(b"section_start:10:step_script\n", {"id": 1}, "2026-10-04T01:00:00Z")
        phase = result["phases"][0]
        self.assertEqual((phase["label"], phase["category"]), ("execute_script", "other"))
        self.assertFalse(phase["complete"])
        self.assertIsNone(phase["duration_seconds"])
        self.assertIsNone(phase["start_seconds"])
        self.assertIn("incomplete_sections", result["limitations"])

    def test_buildkit_duration_position_and_safe_categories(self):
        result = self.parse("2026-10-04T00:00:02.123456Z #1 [internal] load build definition from SECRET.Dockerfile\n"
                            "2026-10-04T00:00:04.5Z #1 DONE 2.25s\n"
                            "2026-10-04T00:00:05Z #2 [stage 1/2] RUN npm ci --password=SECRET\n"
                            "2026-10-04T00:00:15Z #2 DONE 10.0s\n")
        operations = result["builds"][0]["operations"]
        self.assertEqual(operations[0]["category"], "builder_startup")
        self.assertEqual((operations[0]["duration_seconds"], operations[0]["start_seconds"], operations[0]["end_seconds"]), (2.25, 2.25, 4.5))
        self.assertEqual(operations[0]["timing_source"], "buildkit_reported")
        self.assertEqual(operations[0]["position_source"], "log_timestamps")
        self.assertEqual(operations[1]["category"], "dependencies")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["timestamp_lines"], 4)

    def test_redraws_and_repeated_header_are_deduplicated(self):
        result = self.parse("\x1b[1A#1 [internal] load build context\r#1 [internal] load build context\n"
                            "#1 DONE 1.2s\r#1 DONE 1.2s\n"
                            "#1 [internal] load build context\n#1 DONE 1.2s\n")
        self.assertEqual(len(result["builds"]), 1)
        self.assertEqual(len(result["builds"][0]["operations"]), 1)
        operation = result["builds"][0]["operations"][0]
        self.assertEqual(operation["category"], "context_copy")
        self.assertEqual(operation["duration_seconds"], 1.2)
        self.assertIsNone(operation["start_seconds"])
        self.assertEqual(operation["position_source"], "unknown")

    def test_completed_builds_reuse_step_numbers(self):
        result = self.parse("#1 [internal] load build context\n#1 DONE 1s\n"
                            "#2 exporting to image\n#2 DONE 2s\n"
                            "#1 [internal] load build context\n#1 DONE 3s\n"
                            "#2 exporting to image\n#2 DONE 4s\n")
        self.assertEqual(len(result["builds"]), 2)
        first, second = result["builds"]
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["operations"][0]["id"], second["operations"][0]["id"])
        self.assertEqual(second["operations"][0]["duration_seconds"], 3)

    def test_ambiguous_reuse_does_not_merge_independent_steps(self):
        result = self.parse("#1 [internal] load build context\n#1 DONE 1s\n"
                            "#1 [internal] load metadata for SECRET\n#1 DONE 2s\n")
        self.assertEqual(len(result["builds"]), 2)
        self.assertIn("ambiguous_build_boundary", result["limitations"])

    def test_cached_and_partial_steps_are_not_measured_zero(self):
        result = self.parse("#1 [internal] load metadata for SECRET\n#1 CACHED\n"
                            "#2 [stage 1/1] RUN SECRET_TOOL SECRET_ARGUMENT\n")
        cached, partial = result["builds"][0]["operations"]
        self.assertTrue(cached["cached"])
        self.assertIsNone(cached["duration_seconds"])
        self.assertTrue(cached["complete"])
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["category"], "other")
        self.assertEqual(partial["label"], "unknown_operation")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_export_children_dedup_and_parent_cost_is_preserved(self):
        result = self.parse("2026-10-04T00:00:10Z #1 exporting to image\n"
                            "2026-10-04T00:00:14Z #1 4.0 exporting layers 4.0s done\n"
                            "2026-10-04T00:00:14Z #1 4.0 exporting layers 4.0s done\n"
                            "2026-10-04T00:00:15Z #1 5.0 unpacking to SECRET 1.0s done\n"
                            "2026-10-04T00:00:16Z #1 DONE 6.0s\n")
        build = result["builds"][0]
        operation = build["operations"][0]
        self.assertEqual(operation["duration_seconds"], 6)
        self.assertEqual(len(operation["substeps"]), 2)
        self.assertEqual([step["duration_seconds"] for step in operation["substeps"]], [4, 1])
        self.assertEqual((build["start_seconds"], build["end_seconds"], build["span_seconds"]), (10, 16, 6))
        self.assertEqual(build["push_coverage"], "unknown")

    def test_command_intervals_only_end_at_commands_or_script_end(self):
        result = self.parse("section_start:1791072000:step_script\n"
                            "2026-10-04T00:00:01Z $ npm ci --token SECRET\n"
                            "2026-10-04T00:00:02Z SECRET OUTPUT\n"
                            "2026-10-04T00:00:07Z $ PRIVATE_CMD SECRET\n"
                            "section_end:1791072010:step_script\n")
        commands = result["commands"]
        self.assertEqual([command["duration_seconds"] for command in commands], [6, 3])
        self.assertEqual([command["category"] for command in commands], ["dependencies", "other"])
        self.assertTrue(all(command["timing_source"] == "logged_interval" for command in commands))
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("PRIVATE_CMD", json.dumps(result))

    def test_push_coverage_recorded_and_outside(self):
        recorded = self.parse("#1 exporting to image\n#1 1.0 pushing layers 1.0s done\n#1 DONE 2s\n")
        self.assertEqual(recorded["builds"][0]["push_coverage"], "recorded")
        outside = self.parse("#1 exporting to image\n#1 DONE 2s\n2026-10-04T00:00:04Z $ docker push SECRET\n")
        self.assertEqual(outside["builds"][0]["push_coverage"], "outside")

    def test_plain_export_children_without_elapsed_prefix(self):
        result = self.parse("#1 exporting to image\n#1 exporting layers\n"
                            "#1 exporting layers 3.0s done\n#1 exporting manifest SECRET 0.5s done\n"
                            "#1 unpacking to SECRET 1.0s done\n#1 DONE 4.5s\n")
        self.assertEqual(len(result["builds"]), 1)
        operation = result["builds"][0]["operations"][0]
        self.assertEqual(operation["duration_seconds"], 4.5)
        self.assertEqual([step["label"] for step in operation["substeps"]],
                         ["export_layers", "export_manifest", "unpack_local"])
        self.assertEqual([step["duration_seconds"] for step in operation["substeps"]], [3, 0.5, 1])

    def test_pending_build_boundary_survives_initial_progress_before_header(self):
        result = self.parse("#1 [internal] load build context\n#1 DONE 1s\n"
                            "2026-10-04T00:00:02Z $ docker build SECRET\n"
                            "#1 0.0 loading\n#1 [internal] load build context\n#1 DONE 2s\n")
        self.assertEqual(len(result["builds"]), 2)
        self.assertEqual(result["builds"][1]["operations"][0]["category"], "context_copy")
        self.assertEqual(result["builds"][1]["operations"][0]["duration_seconds"], 2)
        self.assertEqual(result["builds"][1]["operations"][0]["first_line"], 4)

    def test_completed_export_redraw_on_same_physical_line_is_not_new_build(self):
        result = self.parse("#1 exporting to image\r#1 DONE 2s\r#1 exporting to image\r#1 DONE 2s\n")
        self.assertEqual(len(result["builds"]), 1)
        self.assertEqual(result["builds"][0]["operations"][0]["duration_seconds"], 2)
        self.assertIn("duplicate_frames", result["limitations"])

    def test_incomplete_child_marks_partial_evidence_without_truncated_fetch(self):
        result = self.parse("#1 exporting to image\n#1 exporting layers\n#1 DONE 3s\n")
        self.assertEqual(result["trace_status"], "available")
        self.assertIn("incomplete_substeps", result["limitations"])

    def test_manifest_and_manifest_list_are_distinct_substeps(self):
        result = self.parse("#1 exporting to image\n"
                            "#1 exporting manifest SECRET 0.1s done\n"
                            "#1 exporting manifest list SECRET 0.2s done\n#1 DONE 0.3s\n")
        children = result["builds"][0]["operations"][0]["substeps"]
        self.assertEqual([item["label"] for item in children], ["export_manifest", "export_manifest_list"])

    def test_done_without_duration_and_partial_span_are_explicit(self):
        result = self.parse("#1 [internal] load build context\n"
                            "2026-10-04T00:00:02Z #1 DONE 1s\n"
                            "#2 [internal] load metadata for SECRET\n#2 DONE\n")
        self.assertEqual(result["builds"][0]["span_seconds"], 1)
        self.assertIn("partial_build_span", result["limitations"])
        self.assertIn("missing_operation_durations", result["limitations"])

    def test_invalid_timing_never_creates_negative_or_nonfinite_values(self):
        result = self.parse("section_start:1791072009:get_sources\nsection_end:1791072001:get_sources\n"
                            "2026-10-04T00:00:01Z #1 [internal] load build context\n"
                            "2026-10-04T00:00:02Z #1 DONE 99s\n")
        self.assertIsNone(result["phases"][0]["duration_seconds"])
        operation = result["builds"][0]["operations"][0]
        self.assertEqual(operation["duration_seconds"], 99)
        self.assertIsNone(operation["start_seconds"])
        self.assertIsNone(operation["end_seconds"])
        json.dumps(result, allow_nan=False)

    def test_non_elapsed_resolve_and_transfer_are_progress_not_build_headers(self):
        result = self.parse("#1 [internal] load build context\n"
                            "#1 transferring context: SECRET 0.5s done\n#1 DONE 0.5s\n"
                            "#2 [stage 1/1] FROM SECRET\n#2 resolve SECRET 1.0s done\n"
                            "#2 sha256:SECRET download\n#2 DONE 1.0s\n")
        self.assertEqual(len(result["builds"]), 1)
        operations = result["builds"][0]["operations"]
        self.assertEqual([item["category"] for item in operations], ["context_copy", "base_image"])
        self.assertEqual([item["duration_seconds"] for item in operations], [0.5, 1])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_identical_restarted_completed_build_has_ambiguous_boundary_code(self):
        result = self.parse("#1 [internal] load build context\n#1 DONE 1s\n"
                            "#2 exporting to image\n#2 DONE 1s\n"
                            "#1 [internal] load build context\n#1 DONE 2s\n")
        self.assertEqual(len(result["builds"]), 2)
        self.assertIn("ambiguous_build_boundary", result["limitations"])

    def test_multiline_shell_retry_after_error_is_a_separate_build(self):
        for terminal in ("ERROR: private failure", "CANCELED"):
            with self.subTest(terminal=terminal):
                result = self.parse("2026-10-04T00:00:00Z $ for attempt in 1 2; do docker build SECRET; done\n"
                                    "#1 [internal] load build definition from SECRET\n"
                                    "2026-10-04T00:00:01Z #1 DONE 1s\n"
                                    "#2 [stage 1/1] RUN npm ci --token SECRET\n"
                                    f"2026-10-04T00:00:10Z #2 {terminal}\n"
                                    "#1 [internal] load build definition from SECRET\n"
                                    "2026-10-04T00:00:12Z #1 DONE 1s\n"
                                    "#2 [stage 1/1] RUN npm ci --token SECRET\n"
                                    "2026-10-04T00:00:22Z #2 DONE 10s\n")
                self.assertEqual(len(result["builds"]), 2)
                first, retry = result["builds"]
                self.assertEqual(first["operations"][0]["duration_seconds"], 1)
                self.assertFalse(first["operations"][1]["complete"])
                self.assertIsNone(first["operations"][1]["duration_seconds"])
                self.assertEqual(first["operations"][1]["last_line"], 5)
                self.assertEqual(retry["operations"][0]["first_line"], 6)
                self.assertEqual(retry["operations"][0]["start_seconds"], 11)
                self.assertEqual(retry["operations"][1]["duration_seconds"], 10)
                self.assertEqual(retry["operations"][1]["start_seconds"], 12)
                self.assertNotEqual(first["operations"][1]["id"], retry["operations"][1]["id"])
                self.assertIn("ambiguous_build_boundary", result["limitations"])
                self.assertNotIn("SECRET", json.dumps(result))

    def test_error_retry_preserves_different_reported_definition_durations(self):
        result = self.parse("2026-10-04T00:00:01Z #1 [internal] load build definition from Dockerfile\n"
                            "2026-10-04T00:00:02Z #1 DONE 1s\n"
                            "2026-10-04T00:00:03Z #2 [stage 1/1] RUN npm ci\n"
                            "2026-10-04T00:00:04Z #2 ERROR process did not complete\n"
                            "2026-10-04T00:00:05Z #1 [internal] load build definition from Dockerfile\n"
                            "2026-10-04T00:00:08Z #1 DONE 3s\n"
                            "2026-10-04T00:00:09Z #2 [stage 1/1] RUN npm ci\n"
                            "2026-10-04T00:00:19Z #2 DONE 10s\n")
        self.assertEqual(len(result["builds"]), 2)
        first, retry = result["builds"]
        self.assertEqual(first["operations"][0]["duration_seconds"], 1)
        self.assertFalse(first["operations"][1]["complete"])
        self.assertIsNone(first["operations"][1]["duration_seconds"])
        self.assertEqual([operation["duration_seconds"] for operation in retry["operations"]], [3, 10])
        self.assertEqual([(operation["start_seconds"], operation["end_seconds"])
                          for operation in retry["operations"]], [(5, 8), (9, 19)])
        self.assertEqual(retry["operations"][0]["first_line"], 5)
        self.assertEqual(first["operations"][1]["last_line"], 4)
        self.assertIn("ambiguous_build_boundary", result["limitations"])

    def test_different_platform_manifests_have_distinct_safe_children(self):
        result = self.parse("#1 exporting to image\n"
                            "2026-10-04T00:00:02Z #1 exporting manifest sha256:SECRET_AAA 1s done\n"
                            "2026-10-04T00:00:05Z #1 exporting manifest sha256:SECRET_BBB 3s done\n"
                            "2026-10-04T00:00:05Z #1 exporting manifest sha256:SECRET_BBB 3s done\n"
                            "2026-10-04T00:00:06Z #1 DONE 6s\n")
        children = result["builds"][0]["operations"][0]["substeps"]
        self.assertEqual(len(children), 2)
        self.assertEqual([item["duration_seconds"] for item in children], [1, 3])
        self.assertEqual([(item["start_seconds"], item["end_seconds"]) for item in children], [(1, 2), (2, 5)])
        self.assertEqual([item["label"] for item in children], ["export_manifest", "export_manifest"])
        self.assertNotEqual(children[0]["id"], children[1]["id"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_explicit_runner_log_limit_marks_available_bytes_partial(self):
        result = self.parse("#1 exporting to image\n#1 DONE 1s\n"
                            "\x1b[33mJob's log exceeded limit of 4194304 bytes.\x1b[0m\n"
                            "Job execution will continue but no more output will be collected.\n")
        self.assertEqual(result["trace_status"], "partial")
        self.assertIn("runner_log_truncated", result["limitations"])
        self.assertNotIn("truncated_trace", result["limitations"])
        self.assertEqual(result["builds"][0]["operations"][0]["duration_seconds"], 1)

    def test_only_identical_completed_child_records_are_deduplicated(self):
        result = self.parse("#1 exporting to image\n"
                            "#1 exporting manifest SECRET 1s done\n"
                            "#1 exporting manifest SECRET 3s done\n"
                            "#1 exporting manifest SECRET 3s done\n#1 DONE 4s\n")
        children = result["builds"][0]["operations"][0]["substeps"]
        self.assertEqual([item["duration_seconds"] for item in children], [1, 3])
        self.assertEqual(len({item["id"] for item in children}), 2)

    def test_after_script_end_closes_estimated_command_interval(self):
        result = self.parse("section_start:1791072000:after_script\n"
                            "2026-10-04T00:00:01Z $ npm ci --token SECRET\n"
                            "section_end:1791072010:after_script\n")
        command = result["commands"][0]
        self.assertEqual(command["duration_seconds"], 9)
        self.assertEqual((command["start_seconds"], command["end_seconds"]), (1, 10))
        self.assertTrue(command["complete"])
        self.assertEqual(command["timing_source"], "logged_interval")
        self.assertEqual(command["last_line"], 3)
        self.assertNotIn("incomplete_commands", result["limitations"])

    def test_reused_completed_step_with_different_duration_is_separate_evidence(self):
        for with_timestamps in (True, False):
            with self.subTest(timestamps=with_timestamps):
                records = [(1, "#1 [internal] load build context"), (2, "#1 DONE 1s"),
                           (5, "#1 [internal] load build context"), (8, "#1 DONE 3s")]
                raw = "\n".join((f"2026-10-04T00:00:{second:02d}Z " if with_timestamps else "") + body
                                for second, body in records) + "\n"
                result = self.parse(raw)
                self.assertEqual(len(result["builds"]), 2)
                first, retry = result["builds"]
                self.assertEqual(first["operations"][0]["duration_seconds"], 1)
                self.assertEqual(first["operations"][0]["last_line"], 2)
                self.assertEqual(retry["operations"][0]["duration_seconds"], 3)
                self.assertEqual(retry["operations"][0]["first_line"], 3)
                self.assertEqual(retry["operations"][0]["last_line"], 4)
                self.assertEqual(retry["operations"][0]["category"], "context_copy")
                self.assertIn("ambiguous_build_boundary", result["limitations"])
                if with_timestamps:
                    self.assertEqual((retry["operations"][0]["start_seconds"],
                                      retry["operations"][0]["end_seconds"]), (5, 8))

    def test_identical_timestamped_completed_progress_is_still_deduplicated(self):
        result = self.parse("2026-10-04T00:00:01Z #1 [internal] load build context\n"
                            "2026-10-04T00:00:02Z #1 DONE 1s\n"
                            "2026-10-04T00:00:05Z #1 [internal] load build context\n"
                            "2026-10-04T00:00:08Z #1 DONE 1s\n")
        self.assertEqual(len(result["builds"]), 1)
        operation = result["builds"][0]["operations"][0]
        self.assertEqual(operation["duration_seconds"], 1)
        self.assertEqual((operation["start_seconds"], operation["end_seconds"]), (1, 2))
        self.assertIn("duplicate_frames", result["limitations"])

    def test_empty_and_truncated_states(self):
        result = self.parse("")
        self.assertEqual(result["trace_status"], "empty")
        self.assertEqual(result["trace_lines"], 0)
        partial = self.parse("#1 exporting to image\n", truncated=True)
        self.assertEqual(partial["trace_status"], "partial")
        self.assertIn("truncated_trace", partial["limitations"])
        self.assertEqual(partial["parser_version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
