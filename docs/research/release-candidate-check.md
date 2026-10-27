# Technical candidate verification — 2026-10-27

Status: local technical candidate verified. This is not a registry publication, external usability acceptance or production-readiness claim. The owner put the five-person usability study on hold on 2026-10-27 so development and technical-preview preparation can continue.

## Build and installed package

From the repository root:

```sh
uv build
uv run --locked python scripts/check_release.py --dist dist
uv run --locked --extra dev pytest tests/integration/test_release.py -q
```

The build produces `forecast_anything-0.1.0.tar.gz` and `forecast_anything-0.1.0-py3-none-any.whl`. The wheel checker installs in a new environment outside the checkout and runs the packaged synthetic example. The report confirms package version `0.1.0`, API schema `1.0.0`, the expected baseline result, required files and licenses, and no detected embedded credentials or model weights in the wheel.

Inspecting the source archive exposed local scratch files under `.superpowers` and a nested `.local/.../.env.example`. Hatch's default VCS filtering did not exclude all these paths. Explicit recursive sdist exclusions now omit local state, agent work material, outputs and build artifacts. A regression test builds an isolated project containing representative private work files and checks that they are excluded while code, contracts, examples and license remain present. `uv build` builds the wheel from the source archive, exercising its buildability.

## Fresh baseline container workspace

Docker Desktop was started for the check. A dedicated Compose project and temporary workspace were created using `scripts/bootstrap_demo.py`, then `docker compose --env-file WORKSPACE/demo.env -f compose.yaml up --build -d --wait`. The workspace contained only a generated token and a synthetic daily CSV: three current-dated rows with values `1, 2, 3`. The source mapped availability to event time explicitly and used UTC, Gregorian daily cadence, revision `1` and unit `count`.

Verified through the built images and authenticated API:

- Core healthy, worker and console running; console HTTP 200.
- Preview resolved the mapping; activation produced the source's discovery snapshot and an executable `expected_deviation` candidate.
- An explicit run submission used that candidate and snapshot. The real seasonal-naive provider returned `[[2.0]]`: the candidate declares period 2, repeating the penultimate observation.
- Repeating the identical submission returned the original job ID.
- Restarting both core and worker preserved the entire issued run unchanged.
- The dedicated stack, its network and temporary workspace were removed afterward.

No optional agent, model weights or external provider request was used. The separate [Compose agent startup smoke](compose-agent-smoke.md), [bounded live agent smoke](../decisions/agent-runtime.md), [Timestral parity and benchmark](../implementation/timestral.md) and [joint-trajectory experiment](joint-paths.md) retain their own limits.

## Contributor and publication status

The three starter scopes are published as [HTTP pagination #9](https://github.com/francescogabrieli/forecast_anything/issues/9), [public-series recipe #10](https://github.com/francescogabrieli/forecast_anything/issues/10) and [difference operator #11](https://github.com/francescogabrieli/forecast_anything/issues/11). Their implementations remain future contributions.

Before publishing packages or images, resolve the public name, owner and registry destinations and select the artifact revision to publish. External usability remains unvalidated and on hold; no participant result has been inferred from automated checks.
