const $ = (s) => document.querySelector(s);
const names = {
  retail: "Retail item totals",
  energy: "Electric power",
  activity: "Page views",
};
const date = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const hour = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});
const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
let currentChart;
function paint(e) {
  const label = (t) =>
    (e.cadence === "hourly" ? hour : date).format(new Date(t));
  const points = [...e.observations, ...e.forecast];
  $("#series").textContent = names[e.id];
  $("#meta").textContent =
    (e.cadence === "hourly"
      ? "Hourly · " + date.format(new Date(e.as_of))
      : "Daily") +
    " · " +
    e.unit +
    " · UTC";
  currentChart = Charts.line($("#chart"), {
    labels: points.map((p) => label(p.time)),
    series: [{ name: names[e.id], values: points.map((p) => p.value) }],
    format: (v) => number.format(v) + " " + e.unit,
    tickFormat: (v) => number.format(v),
    today: e.observations.length - 1,
    todayLabel: "Cutoff",
    height: 198,
  });
  const cell = (tag, value) => {
    const el = document.createElement(tag);
    el.textContent = value;
    return el;
  };
  $("#outputs").replaceChildren(
    ...e.forecast.map((p) => {
      const row = document.createElement("div"),
        val = cell("dd", number.format(p.value) + " ");
      val.append(cell("small", e.unit));
      row.append(cell("dt", label(p.time)), val);
      return row;
    }),
  );
  $("#rows").replaceChildren(
    ...points.map((p, i) => {
      const row = document.createElement("tr");
      row.append(
        cell("td", label(p.time)),
        cell("td", i < e.observations.length ? "Observed" : "Forecast"),
        cell("td", number.format(p.value) + " " + e.unit),
      );
      return row;
    }),
  );
  $("#assumptions").replaceChildren(...e.assumptions.map((a) => cell("li", a)));
  $("#origin").textContent =
    "Issued " +
    e.as_of.replace("T", " ").replace(":00Z", " UTC") +
    " · " +
    e.graph_id +
    " v" +
    e.graph_version;
  $("#snap").textContent = e.snapshot_id;
  $("#run").textContent = e.run_id;
  document
    .querySelectorAll("[data-key]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.key === e.id)),
    );
}
async function start() {
  const response = await fetch("demo-data.json");
  if (!response.ok) return;
  const { examples } = await response.json();
  const records = new Map(examples.map((e) => [e.id, e]));
  paint(records.get("retail"));
  $(".switch").addEventListener("click", (event) => {
    const key = event.target.closest("button")?.dataset.key;
    if (!records.has(key)) return;
    paint(records.get(key));
    $("#status").textContent = names[key] + " selected.";
  });
  $(".switch").hidden = false;
  let width = 0;
  new ResizeObserver(([entry]) => {
    if (width !== entry.contentRect.width) {
      width = entry.contentRect.width;
      currentChart.redraw();
    }
  }).observe($("#chart"));
  document.fonts.ready.then(() => currentChart.redraw());
}
start().catch(() => {}); // The full retail record is available in the static HTML.

const mobileMenu = $(".mobile-nav");
document.addEventListener("click", (event) => {
  if (
    !mobileMenu.contains(event.target) ||
    event.target.closest(".mobile-nav a")
  )
    mobileMenu.open = false;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && mobileMenu.open) {
    mobileMenu.open = false;
    mobileMenu.querySelector("summary").focus();
  }
});

const tourSwitch = document.querySelector(".tour-switch");
function showConsole(view) {
  for (const button of tourSwitch.querySelectorAll("button")) {
    const selected = button.dataset.view === view;
    button.setAttribute("aria-pressed", String(selected));
    document.getElementById(button.getAttribute("aria-controls")).hidden =
      !selected;
  }
}
tourSwitch.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) showConsole(button.dataset.view);
});
showConsole("observatory");
tourSwitch.hidden = false;
