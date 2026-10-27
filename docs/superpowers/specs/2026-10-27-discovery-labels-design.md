# Discovery labels in the observatory

## Intent

Help a new console user understand the kind of question a watch represents while preserving the original candidate rationale for traceability.

## Goals and limits

- Show an Italian title derived from the candidate's registered `template_id`.
- Show the candidate's original `reason` below the title as secondary text.
- Keep lifecycle, quality, priority, and watch actions unchanged.
- Fall back to the original reason (or candidate ID) when the candidate or template is unavailable.
- Do not translate or mutate candidate data in the API.

## Approaches

1. **Localized title plus original reason below — selected.** Uses the trusted template identifier for a concise UI label and retains the submitted reason verbatim. This makes the discovery easier to scan without losing provenance.
2. **Original reason with an expandable explanation.** Preserves current rendering and adds an interaction; less visible to first-time users and keeps the internal English wording prominent.

## Implementation notes

Map the existing `expected_deviation`, `forecast_change`, and `declared_limit` template identifiers to Italian labels in `DiscoveryFeed`. Render the original reason as supporting text. Unknown template IDs retain their current reason-based fallback. No API contract or persistence changes are needed.

## Verification

Add a focused component test for the localized label and the unchanged original reason; keep existing watch states and event rendering intact.
