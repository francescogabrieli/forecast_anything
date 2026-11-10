# Forecast Anything site

The public site is a separate Vite project. React renders its TSX components to HTML at build time; the static output needs no API, browser JavaScript, model weights, or console dependencies. A small client script adds one-time section reveals and a chart replay when motion is enabled. All forecast data and the native evidence disclosure remain available without that script.

From the repository root, with Node 24.5 or later:

```sh
npm --prefix site ci
npm --prefix site run build
npm --prefix site run preview -- --host 127.0.0.1 --port 4176
```

Open [the local preview](http://127.0.0.1:4176/). The generated site is in `site/dist/`; serve that directory with any static HTTP server. For development, use `npm --prefix site run dev`.

The chart reads its observed values from the checked-in [synthetic CSV](../examples/release-demo/observations.csv) and the forecast, baseline and successor from [the recorded run](demo-data.json). The readout and update table use the same record. See the [demo guide](../docs/release-demo.md) for reproduction and limitations. The hero photograph is by Nenad Stojković (Shixart1985). The site uses a resized copy, displayed with a crop and monochrome treatment. [Original photograph on Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Shelves_stocked_with_boxes_and_carts_in_a_spacious_warehouse_environment_during_daylight_hours.jpg) · [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/).

The fonts are bundled locally under the [SIL Open Font License](src/fonts/OFL.txt).

With the preview running, use the console’s existing Playwright installation for browser checks (the console itself does not need to run):

```sh
node site/scripts/check.mjs apps/console/node_modules/playwright/index.mjs /tmp/forecast-site-screens
```

The check covers five viewports, recorded values, links within the static output, and the keyboard path with JavaScript disabled. Pass a local path to `axe.min.js` as the third argument to also check accessibility rules. Set `SITE_URL` to test an alternate preview address.
