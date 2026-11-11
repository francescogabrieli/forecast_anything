# Forecast daily retail sales from a real CSV

**How many items will this retailer sell in the next daily bucket?** [Watch the 30-second replay](media/retail-replay.mp4) to see the CSV confirmation, the forecast and its reference, the historical comparison, and the saved question reopened over a new MCP connection. The video uses captions and values from the recorded SDK run. Its prompts illustrate what to ask an assistant.

## What came back

The assistant workflow used 731 daily observations available by the assumed cutoff of **2 December 2011, 00:00 UTC**. For the daily bucket ending **3 December 2011, 00:00 UTC**, Timestral 28M forecast **27,212 items** and the discovery candidate’s previous-day reference forecast **27,051 items**, both rounded. The later dataset observation was **28,825 items**. The replay recovered the same run and forecast values after reconnecting. The [machine-readable replay record](media/retail-replay.json) includes the exact values, run identity and provider revisions.

The one-day replay illustrates the product workflow. In the separate frozen **five-day** historical comparison, the seven-day seasonal baseline had the lower error:

| Provider | Final MAE, items per day |
| --- | ---: |
| Timestral 28M | 6,300.31 |
| Seven-day seasonal naive | **6,039.84** |

These scores cover **37 matched, non-overlapping final origins** and **185 target values**. Timestral's MAE was **4.31% higher** on this series and split. Lower MAE is better. The [benchmark report](research/timestral-benchmark/report.json), [environment record](research/timestral-benchmark/environment.json) and [benchmark guide](../benchmarks/README.md) give the scope and settings.

## Reproduce the assistant workflow

Prepare the data with the [benchmark commands](../benchmarks/README.md). Follow the [installation guide](installation.md) to connect MCP and prepare Timestral 28M. To replay the same tool sequence with the MCP SDK, use the following from the repo root after preparing the model and installing the MCP extra:

```sh
uv run --locked --extra mcp python scripts/replay_retail_demo.py .local/data/retail.csv
```

The script checks the prepared CSV checksum, writes only the pre-cutoff rows to a temporary workspace, confirms the mapping, queues a forecast, and links it to a saved question. It reconnects over a fresh stdio session and checks the stored forecast for equality. It reads the later observed value from the original benchmark CSV after issuing the forecast. It runs its own local API and worker.

In a connected assistant, copy the [derived three-column CSV](../examples/retail-demo/observations.csv) into an approved local source directory and use the same cutoff. Ask it to preview the daily item totals, confirm the mapping, forecast one day ahead and show the previous-day reference. Ask it to save the question and link the run. After reconnecting, ask it to reopen that question. The replay covers SDK stdio. The clip is an edited presentation of that run. Automatic watching and in-host rendering are outside this replay.

## Data and assumptions

[Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii), Daqing Chen, UCI Machine Learning Repository, DOI 10.24432/C5CG6D, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The [manifest](../benchmarks/manifest.yaml) records the source digest and transformations. The derived series sums positive non-cancelled item quantities by day, across countries and item codes. Empty transaction days are zero under the complete-extract assumption. Daily labels are right endpoints. The source wall clock is interpreted as UTC and availability is assumed at bucket close. Historical release vintages are unavailable.
