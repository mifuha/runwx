"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

const paceMetrics = {
  "median-pace": {
    label: "Median pace",
    value: (edition) => edition.pace.median_s_per_km,
    format: formatPace,
    axis: formatPace,
    lowerIsBetter: true,
  },
  "mean-pace": {
    label: "Mean pace",
    value: (edition) => edition.pace.mean_s_per_km,
    format: formatPace,
    axis: formatPace,
    lowerIsBetter: true,
  },
  "fastest-pace": {
    label: "Fastest 20 median pace",
    value: (edition) => edition.pace.fastest_n_median_s_per_km,
    format: formatPace,
    axis: formatPace,
    lowerIsBetter: true,
  },
};

const weatherMetrics = {
  temperature: {
    label: "Median temperature",
    value: (edition) => edition.weather.median_temperature_c,
    format: (value) => formatNumber(value, "°C", 1),
    axis: (value) => formatNumber(value, "°", 1),
    direction: "Higher means warmer.",
  },
  wind: {
    label: "Median wind",
    value: (edition) => edition.weather.median_wind_mps,
    format: (value) => formatNumber(value, " m/s", 2),
    axis: (value) => formatNumber(value, "", 1),
    direction: "Higher means windier.",
  },
  humidity: {
    label: "Median humidity",
    value: (edition) => edition.weather.median_humidity_pct,
    format: (value) => formatNumber(value, "%", 0),
    axis: (value) => formatNumber(value, "%", 0),
    direction: "Higher means more humid.",
  },
  precipitation: {
    label: "Median precipitation",
    value: (edition) => edition.weather.median_precipitation_mm,
    format: (value) => formatNumber(value, " mm", 1),
    axis: (value) => formatNumber(value, "", 1),
    direction: "Higher means more rain.",
  },
};

const elements = {
  controls: document.querySelector("#comparison-controls"),
  course: document.querySelector("#course-select"),
  paceMetric: document.querySelector("#pace-metric-select"),
  weatherMetric: document.querySelector("#weather-metric-select"),
  status: document.querySelector("#status"),
  comparison: document.querySelector("#comparison"),
  courseName: document.querySelector("#course-name"),
  courseMeta: document.querySelector("#course-meta"),
  paceChartTitle: document.querySelector("#pace-chart-title"),
  paceChartDirection: document.querySelector("#pace-chart-direction"),
  paceChart: document.querySelector("#pace-chart"),
  paceChartCaption: document.querySelector("#pace-chart-caption"),
  weatherChartTitle: document.querySelector("#weather-chart-title"),
  weatherChartDirection: document.querySelector("#weather-chart-direction"),
  weatherChart: document.querySelector("#weather-chart"),
  weatherChartCaption: document.querySelector("#weather-chart-caption"),
  rows: document.querySelector("#comparison-rows"),
};

let comparison = null;
let loadSequence = 0;

function formatPace(value) {
  if (!Number.isFinite(value)) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value - minutes * 60);
  if (seconds === 60) return `${minutes + 1}:00/km`;
  return `${minutes}:${String(seconds).padStart(2, "0")}/km`;
}

function formatNumber(value, suffix, decimals) {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(decimals)}${suffix}`;
}

function formatInteger(value) {
  return Number.isInteger(value) ? value.toLocaleString("en-GB") : "—";
}

function formatChange(value) {
  if (!Number.isFinite(value)) return { text: "—", className: "" };
  if (Math.abs(value) < 0.005) return { text: "Baseline", className: "" };
  const magnitude = Math.abs(value).toFixed(1);
  return value > 0
    ? { text: `+${magnitude}% slower`, className: "change-slower" }
    : { text: `−${magnitude}% faster`, className: "change-faster" };
}

function appendCell(row, text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  row.append(cell);
  return cell;
}

function renderTable(data) {
  elements.rows.replaceChildren();
  for (const edition of data.editions) {
    const row = document.createElement("tr");
    const year = appendCell(row, String(edition.year), "edition-year");
    if (edition.comparison_status !== "comparable") {
      const note = document.createElement("span");
      note.className = "comparison-note";
      note.textContent = edition.comparison_status.replaceAll("_", " ");
      year.append(note);
    }
    appendCell(row, formatInteger(edition.finishers));
    appendCell(row, formatPace(edition.pace.median_s_per_km));
    appendCell(row, formatPace(edition.pace.mean_s_per_km));
    appendCell(
      row,
      `${formatPace(edition.pace.p25_s_per_km)} – ${formatPace(edition.pace.p75_s_per_km)}`,
    );
    appendCell(row, formatPace(edition.pace.fastest_n_median_s_per_km));
    appendCell(row, formatNumber(edition.weather.median_temperature_c, "°C", 1));
    appendCell(row, formatNumber(edition.weather.median_wind_mps, " m/s", 2));
    appendCell(row, formatNumber(edition.weather.median_humidity_pct, "%", 0));
    appendCell(row, formatNumber(edition.weather.median_precipitation_mm, " mm", 1));
    const change = formatChange(edition.change_from_baseline.median_pace_pct);
    appendCell(row, change.text, change.className);
    elements.rows.append(row);
  }
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function renderChart(data, metric, target) {
  const points = data.editions
    .map((edition) => ({ edition, value: metric.value(edition) }))
    .filter((point) => Number.isFinite(point.value));

  target.chart.replaceChildren();
  target.title.textContent = metric.label;
  target.direction.textContent = metric.lowerIsBetter ? "Higher means faster." : metric.direction;

  if (points.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No values are available for this metric.";
    target.chart.append(empty);
    target.caption.textContent = "";
    return;
  }

  const width = 760;
  const height = 230;
  const margin = { top: 18, right: 28, bottom: 42, left: 62 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const values = points.map((point) => point.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const spread = rawMax - rawMin || Math.max(Math.abs(rawMin) * 0.08, 1);
  const min = rawMin - spread * 0.14;
  const max = rawMax + spread * 0.14;

  const x = (index) =>
    margin.left + (points.length === 1 ? plotWidth / 2 : (plotWidth * index) / (points.length - 1));
  const y = (value) => {
    const ratio = (value - min) / (max - min);
    return margin.top + (metric.lowerIsBetter ? ratio : 1 - ratio) * plotHeight;
  };

  const svg = svgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `${metric.label} across ${data.editions.length} ${data.course_name} editions`,
  });

  for (let step = 0; step <= 4; step += 1) {
    const lineY = margin.top + (plotHeight * step) / 4;
    svg.append(
      svgElement("line", {
        x1: margin.left,
        y1: lineY,
        x2: width - margin.right,
        y2: lineY,
        class: "chart-grid",
      }),
    );
    const ratio = metric.lowerIsBetter ? step / 4 : 1 - step / 4;
    const label = svgElement("text", {
      x: margin.left - 10,
      y: lineY + 4,
      "text-anchor": "end",
      class: "chart-axis-label",
    });
    label.textContent = metric.axis(min + ratio * (max - min));
    svg.append(label);
  }

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(point.value)}`)
    .join(" ");
  svg.append(svgElement("path", { d: path, class: "chart-path" }));

  points.forEach((point, index) => {
    const year = svgElement("text", {
      x: x(index),
      y: height - 18,
      "text-anchor": "middle",
      class: "chart-year",
    });
    year.textContent = String(point.edition.year);
    svg.append(year);

    const circle = svgElement("circle", {
      cx: x(index),
      cy: y(point.value),
      r: 5,
      class: "chart-point",
      tabindex: 0,
      role: "img",
      "aria-label": `${point.edition.year}: ${metric.format(point.value)}`,
    });
    const title = svgElement("title");
    title.textContent = `${point.edition.year}: ${metric.format(point.value)}`;
    circle.append(title);
    svg.append(circle);
  });

  target.chart.append(svg);
  target.caption.textContent = `${points.length} of ${data.editions.length} editions have this value.`;
}

function renderCharts(data) {
  renderChart(data, paceMetrics[elements.paceMetric.value], {
    chart: elements.paceChart,
    title: elements.paceChartTitle,
    direction: elements.paceChartDirection,
    caption: elements.paceChartCaption,
  });
  renderChart(data, weatherMetrics[elements.weatherMetric.value], {
    chart: elements.weatherChart,
    title: elements.weatherChartTitle,
    direction: elements.weatherChartDirection,
    caption: elements.weatherChartCaption,
  });
}

function updateUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("course", elements.course.value);
  url.searchParams.set("pace", elements.paceMetric.value);
  url.searchParams.set("weather", elements.weatherMetric.value);
  url.searchParams.delete("metric");
  window.history.replaceState(null, "", url);
}

function render(data) {
  comparison = data;
  elements.courseName.textContent = data.course_name;
  const baseline = data.editions.find((edition) => edition.event_id === data.baseline_event_id);
  const baselineLabel = baseline ? baseline.year : "stated event";
  elements.courseMeta.textContent = `${data.editions.length} editions · ${(data.distance_m / 1000).toFixed(1)} km · baseline ${baselineLabel}`;
  renderTable(data);
  renderCharts(data);
  elements.comparison.hidden = false;
  elements.status.textContent = "";
  elements.status.classList.remove("error");
}

async function loadCourse() {
  const sequence = ++loadSequence;
  updateUrl();
  elements.status.textContent = "Loading comparison…";
  elements.status.classList.remove("error");
  elements.comparison.hidden = true;
  elements.course.disabled = true;

  try {
    const response = await fetch(
      `/api/courses/${encodeURIComponent(elements.course.value)}/comparison`,
      { headers: { Accept: "application/json" } },
    );
    if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
    const data = await response.json();
    if (sequence !== loadSequence) return;
    if (!Array.isArray(data.editions)) throw new Error("Comparison response is invalid");
    render(data);
  } catch (error) {
    if (sequence !== loadSequence) return;
    comparison = null;
    elements.comparison.hidden = true;
    elements.status.textContent = "The comparison could not be loaded. Please try again.";
    elements.status.classList.add("error");
    console.error(error);
  } finally {
    if (sequence === loadSequence) elements.course.disabled = false;
  }
}

function useInitialSelection() {
  const parameters = new URLSearchParams(window.location.search);
  const course = parameters.get("course");
  const paceMetric = parameters.get("pace") ?? parameters.get("metric");
  const weatherMetric = parameters.get("weather");
  if ([...elements.course.options].some((option) => option.value === course)) {
    elements.course.value = course;
  }
  if (Object.hasOwn(paceMetrics, paceMetric)) elements.paceMetric.value = paceMetric;
  if (Object.hasOwn(weatherMetrics, weatherMetric)) elements.weatherMetric.value = weatherMetric;
}

elements.course.addEventListener("change", loadCourse);
elements.paceMetric.addEventListener("change", () => {
  updateUrl();
  if (comparison) renderCharts(comparison);
});
elements.weatherMetric.addEventListener("change", () => {
  updateUrl();
  if (comparison) renderCharts(comparison);
});
elements.controls.addEventListener("submit", (event) => event.preventDefault());

useInitialSelection();
loadCourse();
