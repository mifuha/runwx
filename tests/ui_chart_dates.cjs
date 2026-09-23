const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('src/runwx/api/static/app.js', 'utf8');
const chartCode = source.slice(0, source.indexOf('elements.course.addEventListener'));
function element(name) {
  return {
    name, attributes: {}, children: [], style: {},
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
