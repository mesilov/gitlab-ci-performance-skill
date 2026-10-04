# Bounded trace analysis 2.0.0

The helper uses the authenticated read-only Jobs API through glab. It refreshes
safe metadata for every retained job ID and then requests only available logs in
that scope. It does not retrieve variables or publish raw logs. Without cache,
requests are bounded by 2× retained attempts (at most 64 per selected type).

## Availability and controls

Available, partial, not_run, empty, erased, unavailable and explicitly disabled
states are separate from job outcome. A failed job can have a fully retrieved
log; incomplete sections/operations stay visible as evidence limitations.
Running logs, detected runner recording limits and local byte-cap truncation are
partial. An unavailable GET has a fixed safe error code; transport stderr/body
is not copied. Failed metadata refresh retains an explicitly stale safe projection.

Workers 1–8 (default 4),60 s request timeouts, and `--max-trace-bytes` (default 32 MiB)
bound collection. The stream admits at most cap+1 bytes to detect the cap, then
processes only cap. Received/processed byte counts are distinct; a larger full
source size is unknown. Hashes for capped input describe the processed prefix,
not the unknown complete log. Fixed limitations disclose this. Attempted request counts, fresh-metadata counts
and trace availability counts remain in metadata/report coverage.

With `--trace-cache <dir>`, raw logs remain private (directory 0700/files 0600).
`--reuse-cache` must be explicit. Identity includes host, project ID/path, job ID,
terminal status, finished_at, fetch time, bytes and hash. Future/mismatched/stale,
corrupt, active or partial entries are not reused. Erased logs are not fetched or
restored from cache. Current safe metadata is refreshed even when trace cache
reuse is allowed; original fetch and current analysis times stay visible.
Raw logs and caches never belong in public examples or release artifacts.

## Parser contract

Supports runner section_start/section_end markers, timestamped GitLab output and
plain BuildKit progress. ANSI/CR redraws preserve original newline-based source
line references. Deduplicate repeated frames/operation completion/substeps; keep
step numbers local to stable build IDs. New builds/retries after completed or
failed builds remain separate. Ambiguous reset boundaries are disclosed.

Labels are allowlisted machine codes. Raw command arguments, output, Dockerfile
instructions, image names, digests and destinations are parsed internally only;
unknown evidence gets a generic label. Multi-platform substep identity uses a
private digest fingerprint but only safe ordinal IDs are exported.

- Runner sections: recorded marker timestamps, whole-second precision. Missing
  ends remain incomplete and null.
- BuildKit operations: reported floating durations; positions inferred from
  timestamped completion minus duration when possible. Duration precision differs
  from positional inference. Missing positions remain null, not invented starts.
- Commands: estimates of intervals between logged commands or known script/
  after_script end; not independently profiled command runtime.
- Cached: cached state with missing measured runtime, never fabricated zero cost.

Build spans use known recorded operation intervals and disclose partial coverage.
Parallel operations overlap and must not be summed as job wall time. Push coverage
is recorded/unknown/outside according to available evidence. Export/unpack child
steps remain within their parent cost. Every measurement retains source line
ranges, job URL/log link, raw-byte hash, parser version and analysis time.

An empty/no-supported-evidence state is honest. Durations do not prove disk,
network, cache or runner causes. Fixed optimization directions link to
[Docker cache guidance](https://docs.docker.com/build/cache/optimize/) and relevant
GitLab runner/artifact guidance; they are proposals, not established causes.
