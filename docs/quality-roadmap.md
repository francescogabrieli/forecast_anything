# Quality roadmap

**Status.** This proposal sets the order of work. The current CI checks are the minimum required today. Additional checks should follow as the code and risks make them measurable.

## Current baseline

Every pull request to `main` runs the following checks on Python 3.12 and 3.14:

- Installation consistent with `uv.lock`.
- Ruff lint and formatting checks.
- The pytest suite.
- Wheel and source distribution builds.

Keep the full run fast and reproducible. Run large models, extended benchmarks and checks that require external services in manual or scheduled jobs so pull request checks remain reliable.

## Python file size limit

CI enforces a maximum of **450 lines** for each Python file under `src/`, `tests/` and `scripts/`. The check reads the checkout's Git file list and includes untracked, non-ignored files during local development. It reports the path and line count for every violation. Split files by responsibility as they grow.

Run the same check locally from a Git checkout with `python scripts/check_python_file_lengths.py`.

## Next steps for the Python core

### Controlled dependency updates

Dependabot opens weekly update pull requests for the `uv` lockfile and GitHub Actions. Review each update and run the same CI checks. The repository uses manual merges. GitHub documents the `uv` and `github-actions` identifiers under [supported ecosystems](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories) and [Dependabot version updates](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-version-updates).

The workflow reports results on each pull request. Configure branch protection before merging more code into `main` so it can require both jobs.

## Models, operators and evaluations (Plan 02)

- **Type checking.** Mypy checks `src/`, including bodies of unannotated functions. The checked-in baseline records existing diagnostic counts by file and error code. CI rejects increases, and new files have a zero baseline. Reduce the baseline as existing diagnostics are fixed.
- **Branch coverage.** Coverage.py measures branches in CI. Each Python job publishes a per-file report in its Actions job summary, accessible from the pull request checks. The rollout has no global threshold.
- **Accuracy checks.** PRs run a CPU regression gate on a 32-row synthetic series. The production Timestral adapter runs a tiny, seeded, untrained checkpoint against a fixed seasonal baseline. The gate checks MAE bounds, exact split membership and the input snapshot at each origin, including late revisions. It runs without downloaded weights. Use the manual benchmark workflow and the [checkpoint comparison procedure](../benchmarks/README.md#local-checkpoint-comparison) for broader evidence.
- **Generated invariants.** Hypothesis varies history, cutoffs, delayed revisions and replay inputs. Properties check unchanged forecasts, immutable records after reopening the ledger and rejection of conflicting idempotency keys.
- **Dependency vulnerabilities.** CI runs pip-audit against the locked runtime and MCP dependency set for its Python version. The initial rollout reports findings, skipped packages and tool failures without blocking merges. Review the pinned Timestral Git revision separately. [pip-audit](https://github.com/pypa/pip-audit) is a PyPA tool for finding known vulnerabilities.

### Audit promotion policy

After maintainers have reviewed the initial findings and agreed on remediation, make known High or Critical advisories in shipped dependencies blocking. Use the published CVSS base score of 7.0 or higher or the advisory publisher’s equivalent severity. Keep unscored findings visible for triage. Treat an unavailable advisory service or incomplete scan as a failed check once enforcement is enabled. Any temporary exception must name the advisory and affected dependency, document the reason and owner, and expire on a stated date. The current workflow remains informational.

## API, worker and agents (Plan 03)

- Add integration tests for restarts, expired leases, retries, migrations and fault injection. These exercise the durable work already planned in Plan 03.
- Check API schemas and generated clients so incompatible changes are visible in the pull request.
- Before adding release workflows or broader permissions, add [actionlint](https://github.com/rhysd/actionlint) to check GitHub Actions syntax, expressions and references, and perform a separate static security review. Keep permissions minimal and pin actions to commit SHAs.
- Before public release, enable the GitHub features available to the repository for dependency alerts, secret scanning and push protection. Add CodeQL scanning where the account plan supports it. Availability depends on GitHub settings and the account plan. [GitHub security features](https://docs.github.com/en/code-security/getting-started/github-security-features)

## Console and pre-release checks (Plan 04)

- Format, lint, type-check, test and build the TypeScript code. Add Prettier when the frontend files are introduced.
- Use deterministic data and providers in browser end-to-end tests. Exercise source connection, discovery, comparison and visualization without a live LLM.
- Check links and documented examples. Install the wheel and source distribution in a clean environment outside the checkout, then run the end-to-end quickstart.
- Review licenses and attribution for packages, data and model weights, and inventory the release dependencies.
- Test installation on each platform the project declares supported. Complete that platform matrix before the release. Pull requests can use a smaller matrix.

Plan 04 already includes the frontend build, end-to-end tests, installed-release verification and contributor documentation. This sequence extends those checks.

## Operating rule

For each new required check, identify the risk it catches, define a reproducible result, assign an owner for policy updates and justify its cost. Keep pull request checks fast and deterministic. Run costlier scientific and infrastructure tests manually or on a schedule, with visible results.
