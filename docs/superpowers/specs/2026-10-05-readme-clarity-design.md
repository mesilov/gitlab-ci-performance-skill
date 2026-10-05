# README clarity design — issue #24

Approved scope: [issue #24](https://github.com/mesilov/gitlab-ci-performance-skill/issues/24), accepted for implementation by the user on 2026-10-05.
Base: main at `331dcb7c015e712df72cf3dde9c58d08d3e49c6a`.

Rewrite README.md and README.ru.md with matching sections and commands. Start with
what the skill does, explain job/pipeline/attempt/ref/baseline/provenance, then show
a compact route table, installation and a first canonical report. Keep the reviewed
route and workflow analysis discoverable. Use a small Markdown Mermaid flowchart
and existing synthetic HTML examples. No new frontend or video is required.

Use ASD-STE100-inspired clarity, as requested: simple vocabulary, active verbs,
one main idea per sentence and explicit procedural steps. Adapt these principles
to natural Russian. Do not claim formal compliance or impose a numerical word cap.

A spelling-only edit would leave the onboarding and route ambiguity unresolved.
Moving all technical content out would hide essential limits. The selected approach
keeps practical commands and important restrictions, linking detailed contracts.

Canonical reports preserve original logs and use 16/32 display windows; reviewed
job reports use 32/64 and omit raw logs. Workflow windows count pipelines. Preserve
these distinctions, defaults, update precautions and interpretation limits.

Check local links, Markdown fences, shell syntax, argparse flags and bilingual
command parity. Run documented offline calculations, exports and rendering with
synthetic inputs. Save three before/after examples per language and measured
README size in the verification document. Do not run the full local suite for this
documentation-only change. No parser, calculation, schema or report UI changes.
