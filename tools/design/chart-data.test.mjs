/** Date alignment and no-future-leakage regression tests for the design baseline. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { SOURCE_URL, parseSource, buildChartData, predictForDate, forecastForDate, renderDataBlock, rewriteDataBlock } from "./generate-chart-data.mjs";

const source = parseSource(await readFile(SOURCE_URL, "utf8"));
const chartData = buildChartData(source);

test("90 consecutive replay days and supplied RMSE checkpoints agree", () => {
  assert.equal(chartData.records.length, 90);
  assert.equal(chartData.records[0].date, "2025-03-07");
  assert.equal(chartData.records.at(-1).date, "2025-06-04");
  assert.deepEqual(Object.values(chartData.summary.rmseByPeriod).map((rmse) => rmse.toFixed(1)), ["29.8", "43.6", "46.2"]);
  assert.equal(chartData.summary.tomorrow.predicted.toFixed(1), "277.7");
  assert.equal(chartData.summary.tomorrow.forecastIrradiance.toFixed(1), "27.7");
  assert.equal(chartData.records.at(-1).measured.toFixed(1), "314.1");
  assert.equal(chartData.records.at(-1).predicted.toFixed(1), "276.9");
  assert.equal(chartData.summary.recentWeekMean.toFixed(1), "236.6");
});

test("D forecast uses D-1 Volume, including denominator days", () => {
  const rows = new Map(Array.from({ length: 9 }, (_, index) => [
    `2025-01-${String(index + 1).padStart(2, "0")}`, { measured: (index + 1) * 10, nextDayForecast: index + 1 }
  ]));
  assert.equal(forecastForDate(rows, "2025-01-09"), 8);
  assert.equal(predictForDate(rows, "2025-01-09"), 350 / 28 * 8);
});

test("target-day actual and next-day forecast cannot leak into target prediction", () => {
  const modified = new Map(source);
  modified.set("2025-06-04", { measured: 99999, nextDayForecast: 99999 });
  assert.equal(predictForDate(modified, "2025-06-04"), predictForDate(source, "2025-06-04"));
  for (const date of modified.keys()) if (date > "2025-06-04") modified.delete(date);
  assert.equal(predictForDate(modified, "2025-06-04"), predictForDate(source, "2025-06-04"));
});

test("missing lookback row and zero denominator fail visibly", () => {
  const missing = new Map(source);
  missing.delete("2025-02-27");
  assert.throws(() => buildChartData(missing), /Missing source date/);
  const zeroForecasts = new Map([...source].map(([date, row]) => [date, { ...row, nextDayForecast: 0 }]));
  assert.throws(() => predictForDate(zeroForecasts, "2025-06-04"), /Zero forecast denominator/);
});

test("duplicate dates and invalid numeric values are rejected", () => {
  assert.throws(() => parseSource("Date,Close,Volume,Stop\n2025-01-01,2,3,0\n2025-01-01,3,4,0"), /duplicate date/);
  assert.throws(() => parseSource("Date,Close,Volume,Stop\n2025-01-01,NaN,3,0"), /Invalid generation/);
});

test("regeneration is deterministic and leaves all surrounding code intact", () => {
  const block = renderDataBlock(chartData);
  const script = "before();\n// BEGIN chart-data\nold\n// END chart-data\nafter();";
  const generated = rewriteDataBlock(script, block);
  assert.equal(rewriteDataBlock(generated, renderDataBlock(buildChartData(source))), generated);
  assert.equal(generated, `before();\n${block}\nafter();`);
  assert.throws(() => rewriteDataBlock("no markers", block), /exactly one/);
});
