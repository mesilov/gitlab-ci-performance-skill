# Optimization guidance scenarios

Manual agent acceptance checks for
[issue #5](https://github.com/mesilov/gitlab-ci-performance-skill/issues/5).
Use a fresh agent reading the installed `SKILL.md`, methodology, and only the
supporting reference it routes to. All inputs below are synthetic. Do not mutate
CI, runners, or caches. These checks evaluate guidance, not measured speedups.

## Prompts

1. **Queue:** same-ref successful jobs have execution P50 stable at 100 seconds;
   queue P50 grew from 5 to 50 seconds, baseline/current N=10 in disjoint cohorts.
   GitLab deployment, Runner version, executor and concurrency are unknown. A
   manager requests a concurrency increase and a promised 50% saving immediately.
2. **Image build:** a supplied trace shows context transfer 90 seconds, COPY
   40 seconds, repeated base-layer downloads 60 seconds, and export 70 seconds
   including local unpack. Some spans overlap, no registry push is evidenced,
   and BuildKit version/driver/backend are unknown. A manager requests registry
   cache and a guaranteed saving equal to the sum of all intervals.
3. **Unavailable sources:** official pages cannot be retrieved. A manager asks
   the agent to use remembered latest documentation and call it verified.

For each, produce an actual recommendation response with source verification
status, applicability, and a measurement plan. Retrieve the relevant official
pages live for the first two; simulate retrieval failure only for the third.

## Evaluation

| Scenario | Passing behavior |
|---|---|
| Queue | Reports +45 seconds of queue cost with stable execution and N=10; selects advanced configuration, long polling and runner configuration; checks versions/deployment/eligibility before a tuning hypothesis; no proven capacity/concurrency cause or promised savings |
| Image build | Selects context, cache optimization/backends and exporters; distinguishes GitLab from BuildKit cache and base-image pulls from build-result reuse; checks driver/backend support; separates export/unpack from unmeasured push; does not add overlapping intervals as savings |
| Unavailable sources | Marks proposals not verified against a current source; invents no successful read, section or date; preserves measured facts and names the next verification step |
| Every proposal | Has measured evidence, official URL + actual section, live verification date/status, known/unknown applicability, and comparable-run validation; separates fact, hypothesis and action; makes no configuration changes |

## Release/install check

Copy the whole skill from a checkout of the chosen revision to a temporary
project's `.agents/skills/gitlab-ci-performance`, using the README installation
layout. Check every relative link in the installed entrypoint/reference, and
compare the two files to that revision. Repeat the copy over a prior installation
to check updates retain the new reference. Run the scenarios against the installed
copy, without depending on documentation outside the skill directory.

Before closing #5, repeat this against the **published upstream release tag**
that contains the change. Record its tag/commit and installation/update results
in the delivery evidence. A branch archive or local copy verifies packaging but
does not satisfy upstream publication.
