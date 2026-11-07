# Forecast Anything public site

## Intent

Explain Forecast Anything to developers who already use an assistant with MCP and can run a local Python service. The site should make the product's job concrete, show one reproducible forecast with its assumptions, and lead visitors to the repository and setup guide.

This implements the site responsibility in the approved [MCP-first product direction](2026-10-29-mcp-first-product-design.md) and addresses the first-release gate in [first-release.md](../../first-release.md). It prepares source for review; it does not publish a site or settle the project's public name, domain, owner or package registry.

## Goals

- Give visitors a clear path from understanding the product to running a local forecast through their own assistant.
- Show the checked-in retail, energy and activity examples using results emitted by the production runtime.
- Label synthetic data, provider behavior, timestamp assumptions and point-only limitations beside the demonstration.
- Explain how immutable source snapshots and recorded runs preserve the evidence behind a result.
- Link to the repository, quickstart, MCP guide and contribution guide.
- Keep the page useful on a phone, with keyboard access and reduced-motion support.

## Non-goals

- Hosted forecasting, accounts, an LLM chat, browser uploads or another backend.
- Claiming real-world accuracy, customers, adoption, calibrated uncertainty or general provider superiority.
- Publishing or choosing a public domain, package registry, product owner or trademark.
- Replacing the optional console or changing the Python runtime.

## Approaches

1. **Make the console the public homepage.** This reuses the app but conflicts with the approved direction: the console supports inspection, while the visitor's own assistant is the product entrance.
2. **Build a static page with a purely illustrative mock demo.** This is cheap, but would not demonstrate the actual runtime or its limitations.
3. **Build a buildless static site with a small interactive view backed by the checked-in example outputs.** This keeps public explanation separate from the local console, needs no hosting service, and can display real output from the existing baseline examples. This is the selected implementation.

## Design and behavior

- Use plain HTML, CSS and JavaScript under `site/`; no package installation or runtime server is needed.
- Follow the TasteSkill `product-performs` direction. The site's imagery is the actual forecasting interface: an accessible chart and record fragment made from the repository's example observations and runtime output. Do not add generic stock imagery or decorative fake dashboard elements.
- Carry forward the approved console palette and typography: blue-grey ground, white surfaces, dark ink, restrained teal accent and locally bundled IBM Plex Sans.
- The live example selector switches among retail, energy and activity fixtures. Each state shows input values, forecast values, UTC origin, provider and unit. A text table and explicit synthetic-data explanation accompany the chart.
- Show the supported workflow and boundaries: local source registration, point-in-time snapshot, forecast, later evaluation and recurring watch lifecycle. State that the default baseline is point-only and that MCP connects the visitor's own assistant to a local service.
- The primary action links to the Quickstart; the page also links to the repository, MCP guide and contribution guide. Install instructions must use the source checkout path while no package registry has been approved.
- Keep content and the primary actions available if JavaScript is disabled. Interactive controls must be native buttons with visible focus and clear selected states.

## Acceptance

- A visitor can understand the MCP-first product, run the included example from source, connect the local MCP service, and inspect the boundaries without a hosted account.
- Every plotted value and label comes from an included example or the runtime result; assumptions remain visible.
- The static site loads from a local file server, works at phone and desktop widths, and uses no third-party runtime assets.
- Links point to existing repository resources and no link implies that a package or hosted service has been published.
- Desktop, tablet and mobile layouts, the TasteSkill inspector, keyboard selector, reduced-motion and no-JavaScript fallbacks, chart/table text alternatives, and repository link targets are reviewed before reporting completion.
