# Official sources for optimization recommendations

Read this reference when preparing CI performance improvements. These are
maintained documentation entrypoints, not an offline recommendation catalog.

## Route from measured symptoms

Route link verification date: **2026-10-04**. All 13 distinct starting URLs below
were retrieved successfully; redirects were checked. This date records maintenance
of the route, not source verification for any particular recommendation. Read the
relevant pages again when preparing a proposal and record that verification date.
If a URL moves, resolve its replacement through official documentation and update
the route. Add tool-specific official sources only when the evidence requires them.

| Measured symptom | Official starting points |
|---|---|
| Long pipeline, unnecessary sequencing or repeated work | [Pipeline efficiency](https://docs.gitlab.com/ci/pipelines/pipeline_efficiency/), [needs](https://docs.gitlab.com/ci/yaml/needs/) |
| Runner queue delays | [Advanced runner configuration](https://docs.gitlab.com/runner/configuration/advanced-configuration/), [Long polling](https://docs.gitlab.com/ci/runners/long_polling/), [Configuring runners](https://docs.gitlab.com/ci/runners/configure_runners/) |
| Slow checkout, cache/artifact transfer or executor image preparation | [Speed up job execution](https://docs.gitlab.com/runner/configuration/speed_up_job_execution/), [Configuring runners](https://docs.gitlab.com/ci/runners/configure_runners/), [GitLab caching](https://docs.gitlab.com/ci/caching/) |
| Repeated dependency installation | [GitLab caching](https://docs.gitlab.com/ci/caching/), [Docker cache optimization](https://docs.docker.com/build/cache/optimize/) |
| Large build context or expensive COPY | [Build context](https://docs.docker.com/build/concepts/context/), [Cache optimization](https://docs.docker.com/build/cache/optimize/) |
| Repeated base-layer downloads/unpacking or lost cache between builds | [Cache optimization](https://docs.docker.com/build/cache/optimize/), [Cache storage backends](https://docs.docker.com/build/cache/backends/) |
| Slow image export, local unpack or publication | [Docker exporters](https://docs.docker.com/build/exporters/) |
| Incomplete or unclear timing evidence | [Job logs](https://docs.gitlab.com/ci/jobs/job_logs/), [Jobs API](https://docs.gitlab.com/api/jobs/) |

## Before proposing an optimization

1. Identify the observed queue, execution, phase, or operation cost. Cite the
   snapshot, cohort/sample size, or supplied trace and its timing boundaries.
   If evidence is insufficient, state what must be measured next. The v2 collector fetches bounded retained-job traces and exports allowlisted
   evidence with coverage and origin; legacy 1.x metadata collection does not
   fetch logs. Use measured evidence, not invented phase durations.
2. Read the relevant current official pages and the sections supporting the
   proposed mechanism. A stored URL or remembered recommendation is not live
   verification. Follow official links to more specific guidance as needed.
3. Check applicability to known GitLab, Runner, Docker, Buildx/BuildKit versions,
   executor, builder driver, cache backend, and deployment mode (hosted or
   self-managed; package, Helm, or other installation). Use matching version
   documentation and feature history where available. If a version or setting is
   unknown, state the condition that must hold instead of assuming the latest
   documentation describes the analyzed installation.
4. Keep the following provenance with **each** proposal in the analysis. This is
   an agent workflow; machine-readable recommendation fields remain a separate
   report-schema task.

   | Information | What to record |
   |---|---|
   | Measured fact | Evidence location, observed cost, coverage, and sample size |
   | Causal hypothesis and proposed action | Why the mechanism might explain the cost; what evidence would confirm it |
   | Official source | URL actually read, relevant section title (anchor when available), and verification date |
   | Applicability | Known versions/configuration, supported executor/driver/backend/deployment, unknowns and prerequisites |
   | Validation plan | Before/after comparable runs, affected metric and pipeline wall-clock time, controls, sample size and success criterion |

5. Separate measured facts, causal hypotheses, and proposed actions. If a page
   cannot be retrieved, explicitly mark the proposal **not verified against a
   current source**, identify the unavailable source and unresolved applicability,
   and state the next verification step. Do not invent a successful read, section,
   or verification date. Measured observations remain usable; remembered guidance
   can only support a provisional hypothesis.

## Interpretation checks

- Sum of job durations is not pipeline wall-clock duration. Check the critical
  path before suggesting sequencing changes; preserve real dependencies and
  required outputs.
- Queue duration alone does not establish insufficient runner capacity,
  concurrency limits, or a long-polling cause. For queue growth with stable
  execution, use the runner route to investigate eligible/available runners,
  workload and configuration. Read **Long polling issues** in advanced
  configuration and the long-polling deployment guidance before considering
  `concurrent`, `limit`, or `request_concurrency`; similar timing is not proof.
- GitLab cache and BuildKit cache are different mechanisms. Check the relevant
  driver/backend support and actual import/export configuration before proposing
  a cache. Repeated base-layer downloads do not alone prove lost build-result
  cache: distinguish image pulls, unpacking, cache misses and dependency work.
- For context/COPY costs, read **.dockerignore files** in Build context and
  **Keep the context small** / **Order your layers** in cache optimization. For
  cache lost between builds, read Cache storage backends and verify compatibility
  rather than prescribing a registry cache for an unknown driver.
- Export, local unpack and registry push have different coverage. Read **Load to
  image store** and **Push to registry** in the exporters reference; record actual
  command/output settings and trace boundaries. A build/export interval may omit
  push, so measure publication separately when relevant.
- Category cost is not guaranteed savings. Overlapping intervals cannot simply
  be added. Compare like-for-like workloads, runner resources and image/platform
  inputs, distinguishing cold and warm cache runs and cache-transfer overhead.
  Record failures and sample size as well as queue, execution and wall-clock
  effects; do not promise a percentage speedup without post-change measurements.

Reading documentation or generating proposals does not authorize changes to CI,
runner settings, or caches. Obtain the user's authorization for the actual change.
