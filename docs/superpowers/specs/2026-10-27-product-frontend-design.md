# Product frontend — design for review

Status: approved by the owner in chat on 2026-10-27. The product direction follows the owner's approved journey; this document makes the frontend structure and its implementation boundary concrete.

## Intent

Turn Forecast Anything's technical console into the accessible entrance to its open-source continuous forecasting infrastructure. A person should understand what to do, connect a source, obtain a real forecast and inspect its supporting data, Future Graph and recorded evaluations.

The owner requested a complete frontend redesign using TasteSkill, a polished home with space to start forecasting, and continuity with the approved infrastructure vision. The existing React/TypeScript/Vite app and Python runtime remain the foundation. The five-person usability study is on hold.

## Chosen direction and alternatives

The conversation selects a product home with forecasting inside it. The proposed implementation is one application with a shared shell and focused workspaces. It brings the core task onto the home and uses the same runtime throughout.

Alternatives considered:

- A separate marketing landing page leading to the existing console: easier to present publicly, but leaves the inaccessible source/forecast workflow intact.
- A cosmetic restyle of the existing long console page: smaller change, but keeps workspace credentials, mapping JSON, event logs and scenario JSON competing with the primary task.

One integrated product home fits the agreed purpose. The detailed visual treatment below is the builder's proposal, not an already approved user preference.

## TasteSkill art direction

The app-screen draw offered Achromatic ledger, Framed sheet and Accent ladder. Propose **Framed sheet**, seed 260034763, because the product combines a home, evidence views and a graph workspace used repeatedly.

- A quiet blue-grey frame around a white work surface; restrained teal on forecast data.
- IBM Plex Sans loaded locally with its license; monospace reserved for technical identifiers and code.
- Navigation and surface depth use neutral tones, consistent spacing and few nesting levels.
- Product identity comes from the forecast origin: observations before it, issued future after it, and a graph linking the source to the result. These represent actual data when available.
- A distinct graph-derived mark replaces the current letter in a black box.
- At phone widths the frame becomes a compact header and accessible menu; the task order stays the same.

The reference mentioned in conversation has no verified URL in the repository. This design adopts the described product-home interaction without claiming visual fidelity to an unidentified website.

## Information architecture

### Home — what can I forecast?

Name the product, its purpose and the active workspace. The primary area starts a forecast through a supported source, with a clear action to connect one when the workspace is empty. Show recent real forecasts when present, their dates and provisional/evaluated state. Empty workspaces show an honest empty state and the next action.

For a returning workspace, list registered sources through `GET /sources`. An explicit refresh of the selected source obtains the `SourceRegistration` with discovery job and epoch needed by the first-forecast flow; the source-list response alone does not contain them. Keep retry keys stable across ambiguous responses.

The API has no run-list endpoint. Recent forecasts come from paginated persisted `run_completed` events and their run records; handle histories beyond the first 1,000 events. Failed or incomplete reads must not appear as an empty workspace.

Do not add a natural-language input that cannot execute a supported plan. An editable free-text question belongs to the subsequent natural-language-to-runtime integration, not a decorative home control.

### Sources — what data can the runtime use?

Present registered sources and a guided connection form. Column roles, unit, cadence, timezone, revision and missing-value semantics use labeled controls; advanced JSON remains available for compatibility. Preserve preview, explicit activation, error handling and draft cancellation.

The existing backend supports server-visible CSV paths and HTTP JSON URLs. Label the CSV path accurately. Browser file upload requires a separate storage/ingestion endpoint; do not imply it is implemented by a file-picker facade. If upload is required for the first delivery, expand the implementation plan to include that endpoint before building it.

### Forecasts — what was issued, and what supports it?

Keep explicit first-forecast submission, stale-target rejection, refresh and retry idempotency. Put source, target, value, unit and provisional status ahead of provider IDs and raw run metadata. Render a chart only from the persisted result and compatible recorded observations; preserve gaps and never add uncertainty to point-only output.

The immediately executable first forecast remains one series, one step and the existing seasonal-naive candidate. Label these limits in the creation flow. Do not add arbitrary horizon/model selectors unless their runtime integration is included in a subsequent functional task.

Recorded evaluations are readable beside their result: actuals, metrics supplied by the backend, evaluation origins and assumptions. Absence of an evaluation reads as not yet evaluated. The backend's multi-origin backtesting workflow remains a separate functional milestone; this redesign must not present a historical evaluation as that complete workflow.

### Future Graph and observatory — why, and what changed?

Keep graph keyboard navigation, typed dependency labels, original candidate rationale, watch lifecycle/quality and mute controls. Present graph and evidence near the selected result. Durable events and raw identifiers move into an explicit history/details area. Scenario controls remain connected to the real scenario API; advanced snapshot editing is clearly labeled.

Navigation is functional and preserves the active workspace. Browser back/forward behavior, focus movement and mobile navigation are part of implementation, not decorative links.

## Goals and boundaries

- Every visible action uses the real API or performs a clear local navigation/edit operation.
- Preserve API authentication, in-memory-only tokens, source semantics, immutable evidence and point-in-time behavior.
- Do not invent forecast performance, activity counts, data, confidence bands or autonomous-discovery success.
- Keep technical setup discoverable in workspace settings rather than making it the visual focus of the home. A new workspace still needs a real connection.
- Retain existing capabilities while replacing layout and interaction hierarchy.
- No framework migration, external hosted platform or mandatory cloud account.
- This redesign is one milestone toward the approved complete product, not a claim that accessible upload, multi-origin backtesting or full autonomous discovery are finished.

## Verification and delivery

- Component tests cover navigation, connection state, mapping edits and honest forecast/evaluation states.
- Preserve and adapt both real API/worker Playwright journeys; add browser navigation coverage for the redesigned path.
- Run generated-contract checks, TypeScript, console tests and production build.
- TasteSkill inspection on the production build at 1440, 768 and 390 pixels; open the screenshots, critique and fix issues. Verify keyboard use, reduced motion and empty/loading/error states.
- Independent code review before delivery; commit, push and update/open the relevant PR under the owner's existing authorization.

After design approval, write a task-by-task implementation plan before changing product code. The remaining product milestones retain their order: accessible source ingestion, configurable forecasting and backtesting, continuous question discovery/verification, and installable delivery.
