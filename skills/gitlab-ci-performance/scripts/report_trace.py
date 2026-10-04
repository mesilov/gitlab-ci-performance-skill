"""Project supported log patterns into a closed, secret-free evidence vocabulary.

No log text is returned. BuildKit durations are reported measurements, not a
sequential timeline: concurrent steps are never added to infer an image duration.
Unknown formats remain unsupported; missing boundaries remain partial.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import math
import re

PARSER_VERSION = '1.0.0'
# The source contract bounds each formatted safe summary at 128 KiB. Reserve
# space for provenance; an input cap alone does not bound generated evidence.
MAX_EVIDENCE_NODES = 120
PHASES = frozenset(('prepare_executor', 'prepare_script', 'get_sources', 'restore_cache',
                    'download_artifacts', 'step_script', 'after_script', 'archive_cache',
                    'upload_artifacts', 'cleanup_file_variables'))
STATES = frozenset(('available', 'not_run', 'empty', 'unavailable', 'erased',
                    'permission_denied', 'unsupported', 'partial'))
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
SECTION = re.compile(r'section_(start|end):(\d+):([^\s\[\r]+)')
STAMP = re.compile(r'^\[?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))\]?\s*')
FRAME = re.compile(r'^#(\d+)\s+(.+)$')
DONE = re.compile(r'^DONE\s+(\d+(?:\.\d+)?)s(?:\s|$)')
PART = re.compile(r'^(exporting layers|unpacking to|sending tarball|pushing layers|pushing manifest)(?:\s|$)')
DURATION = re.compile(r'(\d+(?:\.\d+)?)s\s+done(?:\s|$)')


def empty_trace(job_id, state, reason_code, at):
    """Represent a metadata/transport outcome without claiming downloaded bytes."""
    if state not in STATES:
        raise ValueError('invalid trace state')
    return {'job_id': job_id, 'state': state, 'reason_code': reason_code,
            'sha256': None, 'prefix_sha256': None, 'bytes_read': 0, 'line_count': 0,
            'parser_version': PARSER_VERSION, 'fetched_at': at, 'analyzed_at': at,
            'cached': False, 'coverage': {'recognized_lines': 0, 'total_lines': 0,
                                        'truncated': False, 'complete': False}, 'evidence': []}


def _timing(duration=None, start=None, end=None, origin='unknown', quality='unknown', precision=None):
    return {'duration_seconds': duration, 'start_seconds': start, 'end_seconds': end,
            'origin': origin, 'quality': quality, 'precision_seconds': precision}


def _node(identifier, kind, code, parent, line):
    return {'id': identifier, 'kind': kind, 'code': code, 'parent_id': parent,
            'timing': _timing(), 'cached': False, 'complete': False,
            'lines': {'start': line, 'end': line}, 'push_coverage': 'unknown'}


def _precision(number):
    return 10.0 ** -len(number.partition('.')[2]) if '.' in number else 1.0


def _number(value):
    value = float(value)
    return value if math.isfinite(value) else None


def _reported(number):
    value = _number(number)
    return _timing(duration=value, origin='buildkit_reported',
                   quality='exact' if value is not None else 'unknown',
                   precision=_precision(number) if value is not None else None)


def _stamp(line):
    match = STAMP.match(line)
    if not match:
        return None, None, line
    try:
        parsed = datetime.fromisoformat(match[1].replace('Z', '+00:00'))
        value = Decimal(int(parsed.replace(microsecond=0).timestamp()))
    except ValueError:
        return None, None, line
    fraction = re.search(r'\.(\d+)', match[1])
    if fraction:
        value += Decimal('0.' + fraction[1])
    precision = 10.0 ** -len(fraction[1]) if fraction else 1.0
    # GitLab's optional stream token is format metadata, never persisted.
    rest = re.sub(r'^\d\d[OE]\s*', '', line[match.end():])
    return value, precision, rest


def _operation_code(label):
    lower = re.sub(r'^\[[^\]]*\]\s*', '', label).lower()
    if lower.startswith('exporting '):
        return 'export_local_unpack'
    if re.match(r'^(copy|add)\b', lower) or lower.startswith('load build context'):
        return 'context_application_copy'
    if lower.startswith('load metadata for ') or re.match(r'^from\b', lower):
        return 'base_image'
    if re.match(r'^(run|workdir|env|arg|user|shell)\b', lower):
        return 'dependencies_builder_setup'
    return 'other_operation'


def parse_trace(job_id, raw: bytes, *, fetched_at, analyzed_at, truncated=False):
    """Parse already bounded original bytes; caller owns transport/input limits.

    Supports Runner section epochs, ISO8601-prefixed shell echoes, and BuildKit
    plain progress. Repeated step headers with differing labels split ambiguous
    sessions; this deliberately prefers partial evidence to false aggregation.
    """
    result = empty_trace(job_id, 'empty', 'empty_response', fetched_at)
    result['analyzed_at'] = analyzed_at
    digest = hashlib.sha256(raw).hexdigest()
    result['sha256' if not truncated else 'prefix_sha256'] = digest
    result['bytes_read'] = len(raw)
    lines = raw.split(b'\n') if raw else []
    if lines and lines[-1] == b'':
        lines.pop()
    result['line_count'] = len(lines)
    result['coverage'].update(total_lines=len(lines), truncated=bool(truncated), complete=not truncated)
    if not raw:
        if truncated:
            result.update(state='partial', reason_code='input_truncated')
        return result

    evidence = result['evidence']
    recognized = set()
    origin = None
    sections = {}
    command = None
    last_stamp = None
    last_precision = None
    image = None
    sessions = []
    image_times = {}
    image_operations = {}
    banner = None
    counters = {'phase': 0, 'command': 0}
    steps = {}
    labels = {}
    parts = {}
    reports = {}
    first_observed = {}
    ambiguous = False
    evidence_limited = False
    parsed_lines = 0

    def offset(value):
        return _number(value - origin) if value is not None and origin is not None and value >= origin else None

    def new_image(line, stamp, stamp_precision):
        nonlocal image, steps, labels, parts
        image = _node(f'j{job_id}-image-{len(sessions) + 1}', 'image', 'image_build', None, line)
        evidence.append(image)
        sessions.append(image)
        image_operations[image['id']] = []
        image_times[image['id']] = [stamp, stamp, stamp_precision, line, line]
        steps, labels, parts = {}, {}, {}
        return image

    def close_command(end, line, precision, complete):
        nonlocal command
        if command is None:
            return
        timing = command['timing']
        start = timing['start_seconds']
        finish = offset(end)
        valid = start is not None and finish is not None and finish >= start
        timing.update(end_seconds=finish if valid else None,
                      duration_seconds=round(finish - start, 9) if valid else None,
                      quality='inferred' if valid and complete else 'partial',
                      precision_seconds=max(timing['precision_seconds'], precision or 0))
        command['complete'] = bool(valid and complete)
        command['lines']['end'] = max(command['lines']['start'], line)
        command = None

    def reported(node, number, stamp):
        """Retain a reported measurement and candidate endpoints, never log text."""
        if node['cached']:
            return
        value = Decimal(number)
        record = reports.get(node['id'])
        if record is None:
            node['timing'] = _reported(number)
            record = reports[node['id']] = {'duration': value, 'ends': set(), 'conflict': False}
        elif record['duration'] != value:
            record['conflict'] = True
        if stamp is not None and not record['conflict']:
            record['ends'].add(stamp)

    def infer_positions(node, lower=None, upper=None):
        record = reports.get(node['id'])
        if record is None or node['cached'] or node['timing']['duration_seconds'] is None:
            return
        if record['conflict']:
            node['complete'] = False
            node['timing']['quality'] = 'partial'
            return
        # A redraw can report the same completion later. Choose the earliest
        # defensible endpoint, preserving its reported duration and precision.
        for end in sorted(record['ends']):
            start = end - record['duration']
            begin, finish = offset(start), offset(end)
            observed = first_observed.get(node['id'])
            if (begin is None or finish is None or finish < begin or
                    (observed is not None and end < observed) or
                    (lower is not None and begin < lower) or
                    (upper is not None and finish > upper)):
                continue
            node['timing'].update(start_seconds=begin, end_seconds=finish, quality='inferred')
            return

    for line_no, raw_line in enumerate(lines, 1):
        if len(evidence) >= MAX_EVIDENCE_NODES:
            evidence_limited = True
            break
        parsed_lines = line_no
        line = ANSI.sub('', raw_line.decode('utf-8', errors='replace')).strip('\r')
        timestamp, precision, content = _stamp(line)
        section = SECTION.search(content)
        if origin is None:
            anchors = [v for v in (timestamp, Decimal(section[2]) if section else None) if v is not None]
            origin = min(anchors) if anchors else None
        if timestamp is not None:
            last_stamp, last_precision = timestamp, precision

        if section:
            recognized.add(line_no)
            action, epoch, name = section.groups()
            epoch = Decimal(epoch)
            if action == 'start':
                code = name if name in PHASES else 'unknown_phase'
                counters['phase'] += 1
                node = _node(f'j{job_id}-phase-{counters["phase"]}',
                             'phase', code, None, line_no)
                node['timing'] = _timing(start=offset(epoch), origin='section', quality='partial', precision=1.0)
                evidence.append(node)
                sections.setdefault(name, []).append((node, epoch))
            elif sections.get(name):
                node, start = sections[name].pop()
                node['lines']['end'] = line_no
                if epoch >= start and offset(epoch) is not None and node['timing']['start_seconds'] is not None:
                    node['timing'].update(duration_seconds=float(epoch-start), end_seconds=offset(epoch), quality='exact')
                    node['complete'] = True
                if name in ('step_script', 'after_script') and command:
                    close_command(timestamp if timestamp is not None else epoch, line_no, precision or 1.0, True)
            continue

        if timestamp is not None and re.match(r'^\$\s', content):
            recognized.add(line_no)
            close_command(timestamp, line_no - 1, precision, True)
            counters['command'] += 1
            command = _node(f'j{job_id}-command-{counters["command"]}',
                            'command', 'script_command', None, line_no)
            command['timing'] = _timing(start=offset(timestamp), origin='log_interval', quality='partial', precision=precision)
            evidence.append(command)
            continue

        frame = FRAME.match(content.strip())
        if not frame:
            continue
        step, body = frame.groups()
        # Plain frames must carry a recognized header/status; arbitrary # output
        # alone cannot create measured operations or copy data into the summary.
        session_start = body.startswith('building with ')
        header = body.startswith('[') or body.startswith('exporting ') or body.startswith('importing cache ') or body.startswith('preparing build cache ')
        done = DONE.match(body)
        cached = body == 'CACHED'
        part = PART.match(body)
        status = bool(done or cached or body == 'DONE' or body.startswith(('ERROR:', 'CANCELED')))
        if not (session_start or header or status or part or (step in steps and re.match(r'^\d+(?:\.\d+)?\s', body))):
            continue
        recognized.add(line_no)
        if session_start:
            if image is None or banner != body or (steps and all(n['complete'] for n in steps.values())):
                new_image(line_no, timestamp, precision)
            banner = body
            image['lines']['end'] = line_no
            continue
        if image is None:
            new_image(line_no, timestamp, precision)
        # A reused ID with changed header cannot safely belong to the same build.
        if header and not part and step in labels and labels[step] != body:
            ambiguous = True
            image['complete'] = False
            new_image(line_no, timestamp, precision)
        image['lines']['end'] = line_no
        if timestamp is not None:
            previous = image_times[image['id']][1]
            image_times[image['id']][1] = max(timestamp, previous) if previous is not None else timestamp
            image_times[image['id']][2] = max(image_times[image['id']][2] or 0, precision)
            image_times[image['id']][4] = line_no
        if step not in steps:
            if len(evidence) >= MAX_EVIDENCE_NODES:
                evidence_limited = True
                break
            node = _node(f'{image["id"]}-op-{len(steps) + 1}', 'operation', _operation_code(body), image['id'], line_no)
            evidence.append(node)
            image_operations[image['id']].append(node)
            steps[step] = node
            first_observed[node['id']] = timestamp
        node = steps[step]
        node['lines']['end'] = line_no
        if header and not part:
            labels[step] = body
            node['code'] = _operation_code(body)
            if body.startswith('exporting to docker image') or body.startswith('exporting to local') or body.startswith('exporting to tar'):
                if image['push_coverage'] != 'included':
                    image['push_coverage'] = 'excluded'
        if done:
            reported(node, done[1], timestamp)
            node['complete'] = True
        elif cached:
            node['cached'], node['complete'] = True, True
            node['timing'] = _timing()
        elif body == 'DONE':
            node['complete'] = True
        if part:
            semantic = part[1]
            if semantic.startswith('pushing '):
                image['push_coverage'] = 'included'
            node['code'] = 'export_local_unpack'
            key = (step, semantic)
            if key not in parts:
                if len(evidence) >= MAX_EVIDENCE_NODES:
                    evidence_limited = True
                    break
                child = _node(f'{node["id"]}-part-{len(parts) + 1}', 'part', 'export_local_unpack', node['id'], line_no)
                evidence.append(child)
                parts[key] = child
                first_observed[child['id']] = timestamp
            child = parts[key]
            child['lines']['end'] = line_no
            measured = DURATION.search(body)
            if measured:
                reported(child, measured[1], timestamp)
                child['complete'] = True
            elif body.endswith(' done'):
                child['complete'] = True

    close_command(last_stamp, parsed_lines, last_precision, False)
    for node, _ in (item for stack in sections.values() for item in stack):
        node['lines']['end'] = max(node['lines']['end'], parsed_lines)
    for image in sessions:
        children = image_operations[image['id']]
        for child in children:
            infer_positions(child)
        image['complete'] = bool(children) and all(n['complete'] for n in children) and not ambiguous
        image['cached'] = bool(children) and all(n['cached'] for n in children)
        start, end, precision, first_line, last_line = image_times[image['id']]
        if (last_line > first_line and start is not None and end is not None and end >= start
                and offset(start) is not None and offset(end) is not None):
            image['timing'] = _timing(duration=None if image['cached'] else _number(end-start), start=offset(start), end=offset(end),
                                      origin='inferred', quality='inferred' if image['complete'] else 'partial',
                                      precision=precision)
        child_starts = [n['timing']['start_seconds'] for n in children if n['timing']['start_seconds'] is not None]
        child_ends = [n['timing']['end_seconds'] for n in children if n['timing']['end_seconds'] is not None]
        if child_starts and child_ends:
            # Plain progress can arrive after a step began. Its inferred start
            # extends the observed image envelope without clamping the child.
            old = image['timing']
            begin = min(child_starts + ([old['start_seconds']] if old['start_seconds'] is not None else []))
            finish = max(child_ends + ([old['end_seconds']] if old['end_seconds'] is not None else []))
            image['timing'] = _timing(duration=None if image['cached'] else round(finish-begin, 9),
                                      start=begin, end=finish, origin='inferred',
                                      quality='inferred' if image['complete'] else 'partial', precision=precision)
    nodes = {n['id']: n for n in evidence}
    for node in evidence:
        if node['kind'] == 'part':
            parent = nodes[node['parent_id']]
            timing = parent['timing']
            if parent['complete'] and timing['start_seconds'] is not None and timing['end_seconds'] is not None:
                infer_positions(node, timing['start_seconds'], timing['end_seconds'])
    result['coverage']['recognized_lines'] = len(recognized)
    partial = truncated or evidence_limited or any(not n['complete'] for n in evidence)
    result['coverage']['complete'] = not partial
    if not evidence:
        result.update(state='partial' if truncated else 'unsupported',
                      reason_code='input_truncated' if truncated else 'no_supported_patterns')
    elif partial:
        result.update(state='partial', reason_code='input_truncated' if truncated else
                      'evidence_limit' if evidence_limited else 'incomplete_evidence')
    else:
        result.update(state='available', reason_code='parsed')
    return result
