"""Pure allowlisted timing extraction from GitLab runner and BuildKit traces.

Raw strings are used only while parsing. Output labels, categories and limitation
codes are constants, so commands, instructions, image names and output cannot be
copied into published evidence. Positions are relative to the API job start;
reported durations remain useful when that origin or log timestamps are absent.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime

PARSER_VERSION = "2.0.0"
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_ISO = re.compile(r"^\[?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))\]?\s*(?:\d+[OE]\s*)?")
_SECTION = re.compile(r"section_(start|end):(\d+):([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?")
_STEP = re.compile(r"^#(\d+)\s+(.*)$")
_DONE = re.compile(r"^DONE(?:\s+([0-9]+(?:\.[0-9]+)?)s)?\s*$")
_CHILD_DONE = re.compile(r"(?:^|\s)([0-9]+(?:\.[0-9]+)?)s\s+done\s*$", re.I)
_ELAPSED = re.compile(r"^[0-9]+(?:\.[0-9]+)?\s+")
_RUNNER_LOG_LIMIT = re.compile(r"\bJob's log exceeded limit of [0-9]+ bytes\.", re.I)
_PHASES = {
    "prepare_executor": ("prepare_executor", "runner_prepare"),
    "prepare_script": ("prepare_environment", "runner_prepare"),
    "prepare_environment": ("prepare_environment", "runner_prepare"),
    "get_sources": ("checkout_sources", "runner_checkout"),
    "step_script": ("execute_script", "other"),
    "build_script": ("execute_script", "other"),
    "download_artifacts": ("download_artifacts", "runner_artifacts"),
    "upload_artifacts_on_success": ("upload_artifacts", "runner_artifacts"),
    "upload_artifacts_on_failure": ("upload_artifacts", "runner_artifacts"),
    "cleanup_file_variables": ("cleanup", "runner_cleanup"),
    "after_script": ("cleanup", "runner_cleanup"),
}
_CHILDREN = (
    ("exporting layers", "export_layers"),
    ("exporting manifest list", "export_manifest_list"),
    ("exporting manifest", "export_manifest"),
    ("exporting config", "export_config"),
    ("unpacking to", "unpack_local"),
    ("sending tarball", "export_tarball"),
    ("pushing layers", "push_layers"),
    ("pushing manifest", "push_manifest"),
)


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.timestamp() if result.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def _number(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _position(timestamp, origin):
    if timestamp is None or origin is None:
        return None
    return _number(timestamp - origin)


def _evidence(identity, label, category, line, source):
    return {"id": identity, "label": label, "category": category,
            "duration_seconds": None, "start_seconds": None, "end_seconds": None,
            "first_line": line, "last_line": line, "timing_source": source,
            "position_source": "unknown", "cached": False, "complete": False,
            "substeps": []}


def _command_category(command):
    # Match executable + subcommand, never classify by incidental argument text.
    tokens = command.strip().split()
    if len(tokens) > 1 and (
        (tokens[0] in {"npm", "pnpm", "yarn"} and tokens[1] in {"ci", "install", "add"})
        or (tokens[0] in {"pip", "pip3", "poetry", "composer", "bundle"} and tokens[1] == "install")
        or (tokens[0] in {"apt", "apt-get", "apk"} and tokens[1] in {"install", "add"})
        or (tokens[0] == "go" and tokens[1:3] == ["mod", "download"])
    ):
        return "dependencies"
    return "other"


def _operation_category(body):
    text = body.lower()
    instruction = re.sub(r"^\[[^\]]*\]\s*", "", text)
    if instruction.startswith(("exporting ", "unpacking ", "importing cache", "pushing ")):
        return "export_unpack"
    if instruction.startswith(("load build context", "copy ", "add ", "transferring context")):
        return "context_copy"
    if instruction.startswith(("load metadata for", "from ", "resolve image config", "pulling ")):
        return "base_image"
    if instruction.startswith(("load build definition", "load .dockerignore", "booting buildkit", "building buildkit")):
        return "builder_startup"
    if instruction.startswith("run ") and _command_category(instruction[4:]) == "dependencies":
        return "dependencies"
    return "other"


def _reported_timing(item, duration, timestamp, origin, limitations):
    item["duration_seconds"] = duration
    end = _position(timestamp, origin)
    if duration is not None and end is not None and end >= duration:
        item["end_seconds"] = end
        item["start_seconds"] = end - duration
        item["position_source"] = "log_timestamps"
        limitations.add("inferred_operation_positions")
    elif duration is not None:
        # An earlier header is not an independent measured start.
        item["start_seconds"] = None
        item["end_seconds"] = None
        item["position_source"] = "unknown"
        limitations.add("missing_operation_positions")


def parse_trace(raw: bytes, job: dict, analyzed_at: str, truncated: bool = False):
    """Return compact timing evidence without retaining any raw trace strings.

    ``raw`` is the received (possibly bounded) byte stream. Its hash and byte
    count describe those bytes; a collector with a larger known source size must
    record that separately. Incomplete evidence does not imply failed retrieval.
    """
    origin = _timestamp(job.get("started_at"))
    limitations = set()
    if origin is None:
        limitations.add("missing_job_start")
    if truncated:
        limitations.add("truncated_trace")
    phases, builds, commands = [], [], []
    active_sections = {}
    current = None
    pending_command = None
    boundary_pending = False
    lines = raw.decode("utf-8", errors="replace").split("\n")
    if lines and not lines[-1]:
        lines.pop()
    timestamp_lines = set()

    def close_command(timestamp, line):
        nonlocal pending_command
        if pending_command is None:
            return
        item, start = pending_command
        item["last_line"] = line
        if start is not None and timestamp is not None and timestamp >= start:
            item["duration_seconds"] = timestamp - start
            item["end_seconds"] = _position(timestamp, origin)
            item["complete"] = True
            if item["start_seconds"] is not None and item["end_seconds"] is not None:
                item["position_source"] = "log_timestamps"
        else:
            limitations.add("incomplete_commands")
        pending_command = None

    def new_build():
        build = {"id": f"build-{len(builds) + 1}", "label": "image_build",
                 "start_seconds": None, "end_seconds": None, "span_seconds": None,
                 "push_coverage": "unknown", "operations": []}
        builds.append(build)
        return {"public": build, "steps": {}, "headers": {}, "children": {}, "child_counts": {}, "replays": {},
                "closed": False, "failed": False}

    for line_no, physical in enumerate(lines, 1):
        # CR progress frames share the original newline-based line reference.
        clean = _ANSI.sub("", physical)
        inherited_timestamp = None
        for frame in clean.split("\r"):
            text = frame.strip()
            match = _ISO.match(text)
            timestamp = inherited_timestamp
            if match:
                timestamp = _timestamp(match.group(1))
                inherited_timestamp = timestamp
                text = text[match.end():].strip()
                if timestamp is not None:
                    timestamp_lines.add(line_no)
            if _RUNNER_LOG_LIMIT.search(text):
                limitations.add("runner_log_truncated")
            section = _SECTION.search(text)
            if section:
                kind, stamp, name = section.groups()
                stamp = _number(stamp)
                if kind == "start":
                    if name in active_sections:
                        limitations.add("incomplete_sections")
                    label, category = _PHASES.get(name, ("runner_phase", "other"))
                    item = _evidence(f"phase-{len(phases) + 1}", label, category, line_no, "runner_section")
                    item["start_seconds"] = _position(stamp, origin)
                    if item["start_seconds"] is not None:
                        item["position_source"] = "section_markers"
                    phases.append(item)
                    active_sections[name] = (item, stamp)
                elif name in active_sections:
                    item, start = active_sections.pop(name)
                    item["last_line"] = line_no
                    if stamp is not None and start is not None and stamp >= start:
                        item["duration_seconds"] = stamp - start
                        item["end_seconds"] = _position(stamp, origin)
                        item["complete"] = True
                    else:
                        limitations.add("invalid_section_timing")
                    if name in {"step_script", "build_script", "after_script"}:
                        close_command(stamp, line_no)
                else:
                    limitations.add("unmatched_section_end")
                continue

            if text.startswith("$ "):
                command = text[2:]
                close_command(timestamp, line_no)
                category = _command_category(command.lower())
                label = category if category != "other" else "command"
                item = _evidence(f"command-{len(commands) + 1}", label, category, line_no, "logged_interval")
                item["start_seconds"] = _position(timestamp, origin)
                if item["start_seconds"] is not None:
                    item["position_source"] = "log_timestamps"
                commands.append(item)
                pending_command = (item, timestamp)
                limitations.add("estimated_command_intervals")
                if re.match(r"(?:docker|podman)\s+(?:buildx\s+)?build(?:\s|$)", command):
                    boundary_pending = current is not None
                if current and re.match(r"(?:docker|podman)\s+push(?:\s|$)", command):
                    if current["public"]["push_coverage"] == "unknown":
                        current["public"]["push_coverage"] = "outside"
                continue

            step = _STEP.match(text)
            if not step:
                continue
            step_no, body = step.groups()
            done = _DONE.match(body)
            cached = body == "CACHED"
            failed = body.startswith(("ERROR", "CANCELED"))
            progress = _ELAPSED.match(body)
            raw_message = body[progress.end():] if progress else body
            message = raw_message.lower()
            child_kind = next(((prefix, label) for prefix, label in _CHILDREN
                               if message.startswith(prefix)), None)
            header = not (done or cached or failed or progress or child_kind)
            if header and current is not None and step_no in current["steps"]:
                # Plain progress can omit elapsed prefixes: digest transfer and
                # resolution output still belongs to the existing operation.
                header = (body.startswith("[") or body == current["headers"].get(step_no)
                          or body.lower().startswith(("exporting to ", "exporting cache",
                                                      "importing cache", "booting buildkit",
                                                      "building buildkit", "building with ")))
            if current is None:
                current = new_build()
            elif boundary_pending:
                if not current["closed"]:
                    limitations.add("ambiguous_build_boundary")
                current = new_build()
                boundary_pending = False
            elif header and step_no == "1" and (current["closed"] or current["failed"]):
                prior = current["steps"].get(step_no)
                same_frame = (prior is not None and prior["last_line"] == line_no
                              and current["headers"].get(step_no) == body)
                if not same_frame:
                    if current["failed"] or current["headers"].get(step_no) == body:
                        # Without an invocation marker this can also be a
                        # multi-line replay; isolate rather than merge costs.
                        limitations.add("ambiguous_build_boundary")
                    current = new_build()
            elif header and step_no in current["headers"] and current["headers"][step_no] != body:
                limitations.add("ambiguous_build_boundary")
                current = new_build()

            reused_evidence = None
            prior = current["steps"].get(step_no)
            reported_duration = _number(done.group(1)) if done else None
            if (done and prior is not None and prior["complete"] and reported_duration is not None
                    and reported_duration != prior["duration_seconds"]):
                # Identical headers can be a replay until their completion
                # records disagree. Preserve both solves instead of discarding
                # the new duration as another progress frame.
                first_line, previous_end = current["replays"].get(step_no, (line_no, prior["last_line"]))
                prior["last_line"] = previous_end
                reused_evidence = (prior["category"], prior["label"], first_line)
                prior_header = current["headers"].get(step_no)
                limitations.add("ambiguous_build_boundary")
                current = new_build()
                if prior_header is not None:
                    current["headers"][step_no] = prior_header

            if step_no not in current["steps"]:
                category = _operation_category(body) if header else ("export_unpack" if child_kind else "other")
                label = category if category != "other" else "unknown_operation"
                first_line = line_no
                if reused_evidence:
                    category, label, first_line = reused_evidence
                item = _evidence(f"{current['public']['id']}-step-{step_no}", label, category, first_line, "buildkit_reported")
                current["steps"][step_no] = item
                current["public"]["operations"].append(item)
                current["children"][step_no] = {}
                current["child_counts"][step_no] = {}
            item = current["steps"][step_no]
            previous_last_line = item["last_line"]
            item["last_line"] = line_no
            if header:
                if step_no in current["headers"]:
                    limitations.add("duplicate_frames")
                    if item["complete"]:
                        current["replays"].setdefault(step_no, (line_no, previous_last_line))
                elif item["category"] == "other":
                    item["category"] = _operation_category(body)
                    item["label"] = item["category"] if item["category"] != "other" else "unknown_operation"
                current["headers"][step_no] = body
            if done:
                if item["complete"]:
                    limitations.add("duplicate_frames")
                    current["replays"].pop(step_no, None)
                else:
                    item["complete"] = True
                    _reported_timing(item, _number(done.group(1)), timestamp, origin, limitations)
                    if item["category"] == "export_unpack":
                        current["closed"] = True
            elif cached:
                item["cached"] = True
                item["complete"] = True
                item["duration_seconds"] = None
                item["start_seconds"] = None
                item["end_seconds"] = None
                item["position_source"] = "unknown"
            elif failed:
                limitations.add("incomplete_operations")
                current["failed"] = True
            elif child_kind:
                prefix, label = child_kind
                children = current["children"][step_no]
                child_done = _CHILD_DONE.search(raw_message)
                # Target-specific fingerprints distinguish platform manifests
                # without publishing names or digests. Completion fingerprints
                # deduplicate replayed records, rather than all records sharing
                # a label (or even sharing a target).
                target = raw_message[:child_done.start()] if child_done else raw_message
                identity = (label, hashlib.sha256(" ".join(target.split()).encode()).digest())
                group = children.setdefault(identity, {"items": [], "completed": {}})
                signature = hashlib.sha256(" ".join(raw_message.split()).encode()).digest()
                child = group["completed"].get(signature) if child_done else None
                if child is None:
                    child = next((record for record in group["items"] if not record["complete"]), None)
                if child is None and not child_done and group["items"]:
                    child = group["items"][-1]
                if child is None:
                    counts = current["child_counts"][step_no]
                    ordinal = counts.get(label, 0) + 1
                    counts[label] = ordinal
                    suffix = "" if ordinal == 1 else f"-{ordinal}"
                    child = _evidence(f"{item['id']}-{label}{suffix}", label, "export_unpack", line_no, "buildkit_reported")
                    group["items"].append(child)
                    item["substeps"].append(child)
                child["last_line"] = line_no
                if child_done and not child["complete"]:
                    child["complete"] = True
                    _reported_timing(child, _number(child_done.group(1)), timestamp, origin, limitations)
                    group["completed"][signature] = child
                elif child_done:
                    limitations.add("duplicate_frames")
                if prefix.startswith("pushing"):
                    current["public"]["push_coverage"] = "recorded"

    if active_sections:
        limitations.add("incomplete_sections")
        for item, _ in active_sections.values():
            item["last_line"] = len(lines)
    if pending_command:
        pending_command[0]["last_line"] = len(lines)
        limitations.add("incomplete_commands")
    for build in builds:
        operations = build["operations"]
        if any(not item["complete"] for item in operations):
            limitations.add("incomplete_operations")
        if any(not child["complete"] for item in operations for child in item["substeps"]):
            limitations.add("incomplete_substeps")
        if any(item["complete"] and not item["cached"] and item["duration_seconds"] is None
               for item in operations):
            limitations.add("missing_operation_durations")
        intervals = [(item["start_seconds"], item["end_seconds"]) for item in operations
                     if item["start_seconds"] is not None and item["end_seconds"] is not None]
        if intervals:
            build["start_seconds"] = min(start for start, _ in intervals)
            build["end_seconds"] = max(end for _, end in intervals)
            build["span_seconds"] = build["end_seconds"] - build["start_seconds"]
            if len(intervals) != len(operations):
                limitations.add("partial_build_span")
        if build["push_coverage"] == "unknown":
            limitations.add("unknown_push_coverage")
    if raw and not timestamp_lines:
        limitations.add("missing_timestamps")
    partial = truncated or "runner_log_truncated" in limitations
    return {"job_id": job.get("id"), "trace_status": "partial" if partial else ("available" if raw else "empty"),
            "trace_sha256": hashlib.sha256(raw).hexdigest(), "trace_bytes": len(raw),
            "processed_bytes": len(raw), "trace_lines": len(lines), "timestamp_lines": len(timestamp_lines),
            "analyzed_at": analyzed_at, "parser_version": PARSER_VERSION, "phases": phases,
            "builds": builds, "commands": commands, "limitations": sorted(limitations)}
