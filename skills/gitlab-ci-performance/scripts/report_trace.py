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

PARSER_VERSION = '1.2.0'
# The source contract bounds each formatted safe summary at 128 KiB. Reserve
# space for provenance; an input cap alone does not bound generated evidence.
# Source-title provenance increases each node's fixed footprint, so 152 keeps the
# worst supported 128-character identity/title fixture below the 128 KiB cap.
MAX_EVIDENCE_NODES = 152
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
EXPORT_PROGRESS = re.compile(r'^(?:exporting (?:layers|manifest|config|attestation manifest|manifest list)|naming to)(?:\s|$)')
# A digest transfer/extraction is a progress event, never a new header. Its
# text/digest is not retained. FROM may emit cumulative DONE after each layer.
LAYER_PROGRESS = re.compile(r'^(?:extracting )?sha256:[a-f0-9]{64}(?:\s|$)')
NAME_FRAME = re.compile(r'^(naming to|unpacking to) (\S+)(?: (\d+(?:\.\d+)?)s)? done$')
COMPONENT = r'[a-z0-9]+(?:[._-][a-z0-9]+)*'
SENSITIVE = re.compile(r'(?:secret|password|passwd|credential|access[_-]?token|auth[_-]?token|private[_-]?key|api[_-]?key)', re.I)
INSTRUCTION = re.compile(r'^(FROM|RUN|COPY|ADD|ENV|ARG|WORKDIR|USER|SHELL|CMD|ENTRYPOINT|LABEL|EXPOSE|VOLUME|STOPSIGNAL|HEALTHCHECK|ONBUILD)\b', re.I)
SOURCE_LABEL_MAX = 128
SAFE_HEADER_TITLES = frozenset((
    '[internal] load build definition from Dockerfile',
    '[internal] load .dockerignore',
    '[internal] load build context',
    'exporting to image',
    'exporting to docker image format',
    'exporting to oci image format',
    'preparing build cache for export',
))


def _unknown_identity():
    return {'state':'unknown', 'name':None, 'origin':'unknown', 'step_id':None, 'lines':None}


def _unavailable_source_label():
    return {'state':'unavailable', 'text':None, 'origin':'unknown', 'lines':None}


def _label(value, state, origin, line):
    if not value or len(value)>SOURCE_LABEL_MAX or any(ord(char)<32 or ord(char)==127 for char in value):
        return _unavailable_source_label()
    return {'state':state, 'text':value, 'origin':origin,
            'lines':{'start':line, 'end':line}}


def _safe_prefix(prefix):
    """Return a structural BuildKit prefix without retaining arbitrary stage names."""
    if prefix == '[internal]':
        return prefix
    if re.fullmatch(r'\[\d+/\d+\]', prefix):
        return prefix
    match = re.fullmatch(r'\[[^\]]+ (\d+/\d+)\]', prefix)
    return f'[stage {match[1]}]' if match else '[stage]'


def _header_source_label(body, line):
    """Extract a bounded title through a closed grammar; never retain arguments."""
    if body in SAFE_HEADER_TITLES:
        return _label(body, 'original', 'buildkit_header', line)
    prefix, content = '', body
    bracket = re.match(r'^(\[[^\]\r\n]{1,96}\])\s+(.+)$', body)
    if bracket:
        prefix, content = _safe_prefix(bracket[1]), bracket[2]
    instruction = INSTRUCTION.match(content)
    if instruction:
        title = ((prefix+' ') if prefix else '') + instruction[1].upper() + ' [redacted]'
        return _label(title, 'redacted', 'buildkit_header', line)
    if content.startswith('load metadata for '):
        title = ((prefix+' ') if prefix else '') + 'load metadata for [redacted]'
        return _label(title, 'redacted', 'buildkit_header', line)
    if body.startswith('importing cache manifest from '):
        return _label('importing cache manifest from [redacted]', 'redacted',
                      'buildkit_header', line)
    return _unavailable_source_label()


def _part_source_label(semantic, line):
    if semantic == 'unpacking to':
        return _label('unpacking to [redacted]', 'redacted', 'buildkit_progress', line)
    return _label(semantic, 'original', 'buildkit_progress', line)


def _image_name(reference):
    """Validate the whole structured destination; export only its safe basename.

    Registry, repository path, tag and digest are intentionally discarded. No
    shell/URL syntax is accepted; sensitive-looking references are redacted.
    """
    if len(reference)>512 or SENSITIVE.search(reference):
        return None
    base, separator, digest = reference.partition('@')
    if separator and not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        return None
    path = base.split('/')
    leaf, colon, tag = path[-1].partition(':')
    if colon and not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', tag):
        return None
    if len(leaf)>128 or not re.fullmatch(COMPONENT, leaf):
        return None
    for index, component in enumerate(path[:-1]):
        pattern = COMPONENT + (r'(?::[0-9]{1,5})?' if index==0 else '')
        if not re.fullmatch(pattern, component):
            return None
    return leaf


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
            'lines': {'start': line, 'end': line}, 'push_coverage': 'unknown',
            'buildkit': None, 'identity': _unknown_identity() if kind=='image' else None,
            'source_label': _unavailable_source_label() if kind in {'operation','part'} else None}


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
    plain progress. Export suboperations never open sessions. Explicit banners
    after completion/failure open a new session even with identical text/IDs;
    differing genuine headers without a banner remain ambiguous partial builds.
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
    frames_seen = {}
    ambiguous_sessions = set()
    limited_sessions = set()
    failed_sessions = set()
    layer_advanced = set()
    evidence_limited = False
    parsed_lines = 0

    def offset(value):
        return _number(value - origin) if value is not None and origin is not None and value >= origin else None

    def new_image(line, stamp, stamp_precision):
        nonlocal image, steps, labels, parts
        image = _node(f'j{job_id}-image-{len(sessions) + 1}', 'image', 'image_build', None, line)
        steps, labels, parts = {}, {}, {}
        if not admit(image):
            image = None
            return None
        sessions.append(image)
        image_operations[image['id']] = []
        image_times[image['id']] = [stamp, stamp, stamp_precision, line, line]
        return image

    def admit(node):
        nonlocal evidence_limited
        if len(evidence)>=MAX_EVIDENCE_NODES:
            evidence_limited = True
            if image is not None and node['kind'] in {'image','operation','part'}:
                limited_sessions.add(image['id'])
            return False
        evidence.append(node)
        return True

    def identify(match, step, line):
        if match is None:
            return
        name = _image_name(match[2])
        old = image['identity']
        source = 'buildkit_naming' if match[1]=='naming to' else 'buildkit_unpack'
        candidate = {'state':'known' if name else 'redacted', 'name':name,
                     'origin':source, 'step_id':int(step), 'lines':{'start':line,'end':line}}
        if old['state']=='unknown':
            image['identity'] = candidate
        elif old['state']=='known' and name and old['name']==name:
            # Prefer the explicit naming event over a fallback unpacking event.
            if source=='buildkit_naming' and old['origin']=='buildkit_unpack':
                image['identity'] = candidate
            elif source==old['origin'] and int(step)==old['step_id']:
                old['lines']['end']=line
        elif old['state'] not in {'conflicting','redacted'}:
            old.update(state='conflicting' if name else 'redacted', name=None)
            # Keep the first event's resolvable source. A second destination may
            # belong to another export step; never claim its line as step one.

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
        # The budget controls admission, not processing of existing evidence.
        # DONE/section closures and identity must survive an exhausted budget.
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
                accepted = admit(node)
                sections.setdefault(name, []).append((node if accepted else None, epoch))
            elif sections.get(name):
                node, start = sections[name].pop()
                if node is None:
                    continue
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
            if not admit(command):
                command = None
            continue

        frame = FRAME.match(content.strip())
        if not frame:
            continue
        step, body = frame.groups()
        if len(step)>10 or int(step)>2147483647:
            continue
        # Plain frames must carry a recognized header/status; arbitrary # output
        # alone cannot create measured operations or copy data into the summary.
        session_start = body.startswith('building with ')
        header = body.startswith('[') or body.startswith('exporting to ') or body.startswith('importing cache ') or body.startswith('preparing build cache ')
        done = DONE.match(body)
        cached = body == 'CACHED'
        part = PART.match(body)
        export_progress = EXPORT_PROGRESS.match(body)
        layer_progress = LAYER_PROGRESS.match(body)
        naming = NAME_FRAME.fullmatch(body)
        status = bool(done or cached or body == 'DONE' or body.startswith(('ERROR:', 'CANCELED')))
        if not (session_start or header or status or part or export_progress or layer_progress or (step in steps and re.match(r'^\d+(?:\.\d+)?\s', body))):
            continue
        recognized.add(line_no)
        if session_start:
            exported = (any(n['code']=='export_local_unpack' and n['complete'] for n in steps.values())
                        and all(n['complete'] for n in steps.values()))
            if image is None or banner != body or image['id'] in failed_sessions or exported:
                new_image(line_no, timestamp, precision)
            banner = body
            if image is None:
                continue
            image['lines']['end'] = line_no
            continue
        if image is None:
            new_image(line_no, timestamp, precision)
        if image is None:
            continue
        # A reused ID with changed header cannot safely belong to the same build.
        if header and not part and step in labels and labels[step] != body:
            ambiguous_sessions.add(image['id'])
            image['complete'] = False
            new_image(line_no, timestamp, precision)
            if image is None:
                continue
            ambiguous_sessions.add(image['id'])
        image['lines']['end'] = line_no
        existing = steps.get(step)
        record = reports.get(existing['id']) if existing else None
        # Transient digests deduplicate structured progress redraws without
        # retaining their text in the safe summary. Storage is bounded by the
        # caller's physical-line/input budget, like recognized-line accounting.
        signature = hashlib.sha256(body.encode('utf-8')).digest()
        repeated_frame = bool(existing and existing['complete'] and signature in frames_seen.get(existing['id'],set()))
        repeated_completion = bool(done and record and Decimal(done[1])==record['duration'])
        repeated_header = bool(header and existing and existing['complete'] and labels.get(step)==body)
        if timestamp is not None and not (repeated_completion or repeated_header or repeated_frame):
            previous = image_times[image['id']][1]
            image_times[image['id']][1] = max(timestamp, previous) if previous is not None else timestamp
            image_times[image['id']][2] = max(image_times[image['id']][2] or 0, precision)
            image_times[image['id']][4] = line_no
        if step not in steps:
            node = _node(f'{image["id"]}-op-{len(steps) + 1}', 'operation', 'export_local_unpack' if export_progress or part else _operation_code(body), image['id'], line_no)
            node['buildkit'] = {'step_id':int(step)}
            if header:
                node['source_label'] = _header_source_label(body, line_no)
            elif part:
                node['source_label'] = _part_source_label(part[1], line_no)
            if not admit(node):
                continue
            image_operations[image['id']].append(node)
            steps[step] = node
            first_observed[node['id']] = timestamp
        node = steps[step]
        frames_seen.setdefault(node['id'],set()).add(signature)
        node['lines']['end'] = line_no
        identify(naming, step, line_no)
        if layer_progress and node['code']=='base_image' and not repeated_frame:
            layer_advanced.add(node['id'])
            node['complete'] = False
        if header and not part:
            labels[step] = body
            node['code'] = _operation_code(body)
            if node['source_label']['state']=='unavailable':
                node['source_label'] = _header_source_label(body, line_no)
            if body.startswith(('exporting to image', 'exporting to docker image', 'exporting to local', 'exporting to tar')):
                if image['push_coverage'] != 'included':
                    image['push_coverage'] = 'excluded'
        if done:
            record = reports.get(node['id'])
            if (record and node['id'] in layer_advanced and not record['conflict']
                    and Decimal(done[1])>record['duration']):
                # FROM's subsequent digest extraction reports cumulative elapsed
                # time. Replace the earlier checkpoint; never add durations.
                reports.pop(node['id'])
            layer_advanced.discard(node['id'])
            reported(node, done[1], timestamp)
            node['complete'] = True
        elif cached:
            node['cached'], node['complete'] = True, True
            node['timing'] = _timing()
        elif body == 'DONE':
            node['complete'] = True
        elif body.startswith(('ERROR:', 'CANCELED')):
            node['complete'] = False
            failed_sessions.add(image['id'])
        if part:
            semantic = part[1]
            if semantic.startswith('pushing '):
                image['push_coverage'] = 'included'
            node['code'] = 'export_local_unpack'
            key = (step, semantic)
            if key not in parts:
                child = _node(f'{node["id"]}-part-{len(parts) + 1}', 'part', 'export_local_unpack', node['id'], line_no)
                child['buildkit'] = {'step_id':int(step)}
                child['source_label'] = _part_source_label(semantic, line_no)
                if not admit(child):
                    continue
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
        if node is not None:
            node['lines']['end'] = max(node['lines']['end'], parsed_lines)
    for image in sessions:
        children = image_operations[image['id']]
        for child in children:
            infer_positions(child)
        image['complete'] = bool(children) and all(n['complete'] for n in children) and image['id'] not in (ambiguous_sessions | limited_sessions | failed_sessions)
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
