# README clarity implementation plan

> Execute inline with superpowers:executing-plans; user authorized issue #24 in a separate worktree.

**Goal:** Make both READMEs easy to follow without changing technical meaning.
**Architecture:** Matching English/Russian Markdown, a CLI choice table, one flowchart and links to existing contracts.
**Tech Stack:** Markdown, Mermaid, shell examples, existing Python CLIs.

## Task 1: Establish the technical baseline

- [x] Create a worktree from current origin/main and branch codex/issue-24-readme.
- [x] Read both README files, SKILL.md, contract-v2.md and workflows.md.
- [x] Confirm canonical 16/32, reviewed 32/64, pipeline windows and log policies against the implementation.

## Task 2: Rewrite both README files

Files: README.md and README.ru.md.

- [x] Use matching sections: purpose, terms, route choice, install/update, report use/checks, first report, reviewed report, workflow analysis, interpretation, further reading, development.
- [x] Add a simple localized GitLab → collect → calculate → HTML/JSON Mermaid diagram.
- [x] Give complete canonical and reviewed commands with explicit working directory and dependency setup.
- [x] Keep synthetic examples, screenshots, essential privacy and comparison limits; link detailed references.

## Task 3: Verify and deliver

File: docs/superpowers/verification/2026-10-05-readme-clarity.md.

- [x] Check local Markdown links, matching code blocks and balanced fences; run sh -n on shell blocks.
- [x] Check all CLI subcommands and flags through --help, without contacting GitLab.
- [x] Run report/export/render on synthetic canonical data and report/render on reviewed data in a temporary directory.
- [x] Record three before/after examples per language, size changes and exact verification results.
- [x] Review the diff and run git diff --check; prepare the scoped changes for a commit and PR against main.

- [x] Integrate main at 83b50e7 and preserve the instructions added by issue #23.
