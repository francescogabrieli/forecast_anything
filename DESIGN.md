# Forecast Anything design system

The interface should make a forecast easy to read and check. Lead with the metric, target date and result. Place the baseline and relevant assumptions next to the result. Keep detailed evidence available through the same run or question.

## Color

The public site uses a warm cream canvas, ink text and a single burnt orange accent. The darker orange carries text, focus and primary actions. Use the brighter orange for marks and illustrations.

| Role | Color | Use |
| --- | --- | --- |
| Canvas | `#F3EEE3` | Page background and light chart surfaces |
| Ink | `#111111` | Headings, body text and observed series |
| Muted ink | `#514C42` | Captions, units and secondary text |
| Rule | `#B9B1A2` | Section dividers and chart grid lines |
| Burnt orange | `#D9541E` | Forecast marks and graphic accents |
| Dark orange | `#A33B13` | Links, focus outlines and primary buttons with cream text |

Use text and shape alongside color to distinguish chart series and status. Keep subtle rules decorative. Give input boundaries and focus indicators enough contrast to remain visible against the adjacent surface.

## Typography

Use [IBM Plex Sans](site/src/fonts/OFL.txt), bundled under the SIL Open Font License 1.1, for headings, body copy and controls. Use weight 400 for reading and 600 for emphasis. The console also bundles weight 500 under the [same license](apps/console/public/fonts/OFL.txt). Use system sans-serif as the loading fallback and system monospace for commands and identifiers. The site's italic hero emphasis uses a system serif stack.

Use sentence case for headings and controls. Use tabular numerals when comparing values, dates or errors. Keep units with their values and avoid using all caps for sentences.

## Layout

- Align headings, copy, charts and actions to the same page grid. The site uses a maximum content width of `75rem` and fluid side insets.
- Use open spacing and thin rules to separate sections. Reserve bordered panels for grouped controls, results and evidence.
- Keep the main action close to its heading or result. Stack paired content when it needs more room. On narrow screens, confine horizontal scrolling to wide charts and tables.

## Components

| Component | Treatment |
| --- | --- |
| Primary action | Use a filled control with a verb that describes the result, such as “Connect your assistant.” Reserve the strongest treatment for the main action in a group. |
| Secondary action or link | Use an outlined button for a secondary action and an underlined link for navigation. Keep the keyboard focus indicator visible. |
| Form field | Show a persistent label, any required format and validation close to the field. Preserve the entered value when validation fails. |
| Forecast chart | Use an ink line for observations, a filled orange point for a forecast and an outlined diamond for the seasonal baseline. Label the cutoff, target date and unit. For comparisons, keep the target and scale aligned. |
| Result panel | Show the value, unit and target first. Put the comparator and forecast status nearby. Keep supporting evidence accessible through a detail link or disclosure. |
| Status | Use explicit labels such as “Provisional,” “Evaluated” or “Data unavailable.” Add a reason or recovery action when one is available. |
| Table | Label columns and units. Right-align comparable numbers and use stable precision within a column. |

## Motion and accessibility

Keep chart replay user-initiated and show the same values in the static view. Respect reduced-motion preferences. Use motion to show when a value appears or changes. Keep essential information available as text and ensure controls are usable with the keyboard.

## Implementation

The [public site stylesheet](site/src/styles.css) implements the light palette, type and chart marks. The [console stylesheet](apps/console/src/styles.css) currently implements a separate dark theme. Apply this guide's typography, component roles and chart semantics as console screens are updated.
