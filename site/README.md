# Preview the public site

From the repository root, run:

```sh
python3 -m http.server 4174 --bind 127.0.0.1 --directory site
```

Open [the local preview](http://127.0.0.1:4174/). No build, API server, third-party font request or model download is required.

The explorer shows recorded values from three synthetic fixtures, with the forecast cutoff, units, assumptions and record IDs. If JavaScript or the data request is unavailable, the retail example is still readable. When outputs change, rerun the corresponding fixture with `scripts/run_example.py` and refresh both `demo-data.json` and the HTML fallback.

The responsive SVG plot uses the line chart from Taste Skill; the console tour uses current production-build captures of Home and Observatory against the isolated, seeded E2E backend. The public UI follows the repository’s [Linear design reference](../DESIGN.md), imported with `npx getdesign@latest add linear.app`. It uses the specified system font fallback. The site is prepared for local review; it has not been published.

The recorded explorer now uses genuine local Timestral runs, with a separate seasonal reference in the data file. Producing new records requires prepared model weights; viewing the static files does not. Displayed values use three decimal places while the data file retains full precision. Baseline data/HTML before this update were retained privately under `.local/site-baseline-before-timestral/`. This site source is still local and unpublished.
