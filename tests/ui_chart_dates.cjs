const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('src/runwx/api/static/app.js', 'utf8');
const chartCode = source.slice(0, source.indexOf('elements.course.addEventListener'));
function element(name) {
  return {
    name, attributes: {}, children: [], style: {},
    classList: { add() {}, remove() {} },
    setAttribute(key, value) { this.attributes[key] = value; },
    append(...children) { this.children.push(...children); },
    replaceChildren() { this.children = []; },
  };
}
const context = vm.createContext({
  document: {
    querySelector: () => element('div'),
    createElementNS: (_namespace, name) => element(name),
    createElement: (name) => element(name),
  },
  URL, Date, Number, Math, String, Set, Object,
});
vm.runInContext(chartCode, context);

const dates = [
  '2022-03-26', '2022-05-21', '2022-07-16', '2022-08-06',
  '2022-10-15', '2022-11-19', '2023-03-04', '2023-04-22',
  '2023-06-03', '2023-11-11', '2023-12-02', '2024-03-02', '2024-08-03',
];
const data = {
  course_name: 'Battersea Park 10K',
  editions: dates.map((date, index) => ({
    year: Number(date.slice(0, 4)),
    started_at_utc: `${date}T08:30:00Z`,
    pace: { median_s_per_km: 240 + index },
    weather: { median_temperature_c: 5 + index },
  })),
};

function chart(metric) {
  const target = {
    chart: element('div'), title: element('h4'),
    direction: element('p'), caption: element('p'),
  };
  context.chartTarget = target;
  context.chartMetric = metric;
  context.chartData = data;
  vm.runInContext('renderChart(chartData, chartMetric, chartTarget)', context);
  const svg = target.chart.children[0];
  return {
    svg,
    labels: svg.children.filter((child) => child.name === 'text' && child.attributes.class === 'chart-year'),
    points: svg.children.filter((child) => child.name === 'circle'),
  };
}

const pace = chart(vm.runInContext("paceMetrics['median-pace']", context));
const weather = chart(vm.runInContext('weatherMetrics.temperature', context));
for (const rendered of [pace, weather]) {
  assert.equal(rendered.points.length, dates.length);
  assert.equal(Number(rendered.svg.attributes.viewBox.split(' ')[2]), 90 + dates.length * 82);
  assert.ok(rendered.labels.length >= 3 && rendered.labels.length < dates.length);
  assert.equal(rendered.labels[0].textContent, '26 Mar 2022');
  assert.equal(rendered.labels.at(-1).textContent, '3 Aug 2024');
  const chartWidth = Number(rendered.svg.attributes.viewBox.split(' ')[2]);
  assert.ok(Number(rendered.labels[0].attributes.x) >= 62);
  assert.ok(chartWidth - Number(rendered.labels.at(-1).attributes.x) >= 62);
  for (let index = 1; index < rendered.labels.length; index += 1) {
    assert.ok(Number(rendered.labels[index].attributes.x) - Number(rendered.labels[index - 1].attributes.x) >= 96);
  }
  assert.ok(rendered.points.every((point, index) =>
    point.attributes['aria-label'].includes(dates[index].slice(0, 4))));
}
assert.deepEqual(pace.labels.map((label) => label.textContent), weather.labels.map((label) => label.textContent));
assert.notEqual(pace.points[0].attributes.cx, pace.points[1].attributes.cx);
console.log('Battersea chart dates are readable; both plots retain all dated points.');

// Research captures have no baseline, individual start or matched-runner fields.
const research = {
  scope: 'research_capture', course_slug: 'berlin-marathon',
  course_name: 'Berlin Marathon', distance_m: 42195,
  population_note: 'Research capture with retained count gaps.',
  course_note: 'Unknown timing; course era only.',
  editions: Array.from({ length: 16 }, (_, index) => ({
    year: 2003 + index, race_date: `${2003 + index}-09-28`,
    comparison_status: 'descriptive_research_capture',
    accepted_count: 30000, captured_count: 30001, held_count: 1,
    published_count: index === 10 ? null : 29922,
    count_difference_from_published: index === 10 ? null : 79,
    pace: { median_s_per_km: 300 + index, mean_s_per_km: 310,
      p25_s_per_km: 280, p75_s_per_km: 350, fastest_n_median_s_per_km: 200 },
    weather: { median_temperature_c: 10 + index, median_wind_mps: 2,
      median_humidity_pct: 60, precipitation_mm: 0 },
  })),
};
context.testData = research;
vm.runInContext(`
  elements.paceMetric.value = 'median-pace';
  elements.weatherMetric.value = 'precipitation';
  render(testData);
`, context);
const renderedElements = vm.runInContext('elements', context);
assert.equal(renderedElements.rows.children.length, 16);
assert.equal(renderedElements.countHeading.textContent, 'Accepted records');
assert.equal(renderedElements.timingHeading.hidden, true);
assert.equal(renderedElements.publishedHeading.hidden, false);
assert.equal(renderedElements.changeHeading.hidden, true);
assert.ok(!renderedElements.courseMeta.textContent.includes('baseline'));
assert.equal(renderedElements.rows.children[10].children[2].textContent, 'Unknown');
assert.equal(renderedElements.rows.children[5].children[2].children[0].textContent, 'capture difference +79');
assert.equal(renderedElements.rows.children[0].children[1].children[0].textContent, '1 held; 30,001 captured');
assert.equal(renderedElements.rows.children[0].children[10].textContent, '0.0 mm');
assert.equal(renderedElements.weatherChartTitle.textContent, '09:00–15:00 precipitation');
assert.equal(renderedElements.researchDetails.hidden, false);
assert.match(renderedElements.interpretation.textContent, /Timing basis and individual starts are unknown/);
assert.match(renderedElements.interpretation.textContent, /09:00–15:00 Europe\/Berlin/);
assert.ok(parseInt(renderedElements.timeline.style.minWidth, 10) >= 780);
for (const plot of [renderedElements.paceChart, renderedElements.weatherChart]) {
  const svg = plot.children[0];
  const labels = svg.children.filter((child) => child.attributes.class === 'chart-year');
  assert.equal(svg.children.filter((child) => child.name === 'circle').length, 16);
  assert.equal(labels.length, 16);
  assert.equal(labels[0].textContent, '2003');
  assert.equal(labels.at(-1).textContent, '2018');
  for (let index = 1; index < labels.length; index += 1) {
    assert.ok(Number(labels[index].attributes.x) - Number(labels[index - 1].attributes.x) >= 40);
  }
}

const ordinary = {
  course_slug: 'lydd-half', course_name: 'Lydd', distance_m: 21097.5,
  baseline_event_id: 'baseline', editions: [{
    ...research.editions[0], event_id: 'baseline', started_at_utc: '2003-09-28T09:00:00Z',
    comparison_status: 'comparable', finishers: 50,
    change_from_baseline: { median_pace_pct: 0 },
    weather: { ...research.editions[0].weather, precipitation_mm: undefined, median_precipitation_mm: 0.2 },
  }],
};
context.testData = { ...ordinary, scope: 'top_1000', sample_label: 'Top 1,000 only*',
  sample_note: 'Sample, not full field.', editions: [{ ...ordinary.editions[0],
    comparison_status: 'descriptive_sample', sample_size: 1000, median_pace_change_pct: 0,
    timing: { chip: 1000, gun: 0, unknown: 0, note: 'Chip times' },
  }] };
vm.runInContext('render(testData)', context);
assert.equal(renderedElements.countHeading.textContent, 'Sampled results');
assert.equal(renderedElements.timingHeading.hidden, false);
assert.equal(renderedElements.publishedHeading.hidden, true);
assert.equal(renderedElements.changeHeading.hidden, false);
assert.equal(renderedElements.researchDetails.hidden, true);
assert.equal(renderedElements.weatherChartTitle.textContent, '10:00–14:00 precipitation');
assert.equal(renderedElements.rows.children[0].children.at(-1).textContent, 'Baseline');
context.testData = ordinary;
vm.runInContext('render(testData)', context);
assert.equal(renderedElements.countHeading.textContent, 'Finishers');
assert.equal(renderedElements.timingHeading.hidden, true);
assert.equal(renderedElements.weatherChartTitle.textContent, 'Median precipitation');
assert.match(renderedElements.courseMeta.textContent, /baseline 2003/);
assert.equal(renderedElements.rows.children[0].children[9].textContent, '0.2 mm');
console.log('Berlin retains all 16 points, research caveats and count gaps; switching course scopes resets the table.');
