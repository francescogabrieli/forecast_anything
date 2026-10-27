# Discovery labels implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox syntax.

**Goal:** Make watched-question titles understandable in Italian while preserving the candidate's original reason.

**Architecture:** The console maps the existing `template_id` to an Italian title and renders `reason` as secondary text. Unknown templates retain the existing reason/ID fallback.

**Tech Stack:** React, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-27-discovery-labels-design.md`.

## Task 1: Localize watched-question titles

**Files:** `apps/console/src/features/observatory/DiscoveryFeed.tsx`, its existing test, generated API types are unchanged.

- [x] Add a component test proving `expected_deviation` gets an Italian title and preserves the original reason below.
- [x] Run the focused test and confirm it fails on the current raw-English title.
- [x] Render the localized title from `candidate.template_id`, with the reason as secondary copy; preserve fallback behavior.
- [x] Run the focused component suite, typecheck, and formatting checks.
- [x] Original delivery kept uncommitted; the owner authorized commit, push and PR creation on 2026-10-27.
