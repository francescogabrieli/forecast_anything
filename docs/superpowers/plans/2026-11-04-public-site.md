# Public Site Implementation Plan

> Inline execution using `superpowers:executing-plans`; no subagents.

**Goal:** Prepare a truthful, reviewable static onboarding site for the MCP-first Forecast Anything release.

**Architecture:** Buildless HTML/CSS/JavaScript under `site/`. A checked-in data file records the output of the existing synthetic examples; the interface switches among these values without an API or model call. The primary setup link points to the repository Quickstart.

**Spec:** `docs/superpowers/specs/2026-11-04-public-site-design.md`; product direction: `docs/superpowers/specs/2026-10-29-mcp-first-product-design.md`.

## Constraints

- Prepare local source only; no hosting registration, publication or domain choice.
- Keep the console optional and avoid inventing an online service, released package, customer, metric or accuracy claim.
- Site interactions and copy must reflect existing runtime, MCP and worker behavior.
- Preserve the project's local IBM Plex Sans license notice.

## Tasks

### 1. Trace and record real demo data

- [x] Run the included retail, energy and activity examples through `scripts/run_example.py`.
- [x] Add a compact site data file with six source values, three actual forecast values, origin, timestamps, provider, units and synthetic assumptions for each example.
- [x] Keep a visible text representation so the chart is not the only accessible route to the data.

### 2. Build the static page

- [x] Add the responsive semantic page, local font assets, styles and a keyboard accessible example selector.
- [x] Use the TasteSkill `product-performs` direction and real product fragments; do not add fake metrics or decorative stock visuals.
- [x] Explain the local MCP setup, durable evidence flow, current limits and contribution path with existing docs as source of truth.
- [x] Include a no-JavaScript fallback and respect reduced-motion preferences.

### 3. Review and hand off

- [x] Preview locally and inspect desktop, tablet and phone layouts with TasteSkill.
- [x] Check the selector with pointer and keyboard, reduced-motion/no-JavaScript paths in source, chart and table text alternatives, and repository link targets.
- [x] Run the TasteSkill page lint/inspector and `git diff --check`; resolve layout findings and record intentional media warnings and release gates.
- [x] Update README, quickstart, MCP/evidence docs, roadmap and first-release evidence without implying publication.

## Review notes

- TasteSkill direction selected: `product-performs` (`dev-tool`, seed `88889278`). It fits because Forecast Anything's strongest visual proof is a real output with its source and assumptions attached.
- Project imagery adjustment: no customer photographs or deployed dashboard exist. The page uses real fixture outputs and interface fragments, rather than generic generated scenes that could imply customers or hosted functionality.
- TasteSkill review: source lint passes with 0 failures and 0 warnings; rendered inspection has 0 failures. Its only two warnings are intentionally defended: no authentic customer photography or product footage exists, and generic media would misrepresent this developer tool. The real chart and interface fragments are the relevant visual evidence.
- Final inspector result: 0 failures; 2 defended media warnings. Desktop (1440), tablet (768) and phone (390) layouts have no horizontal overflow. The Energy and Activity examples were selected from the keyboard, and the Energy table's six observations and three forecasts matched the recorded output.
- Release remains local-only: public destination/name, publishing, and direct Codex Desktop MCP validation are open decisions/checks.
