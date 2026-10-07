/** Pure selection/aggregation helpers. kWh is summed; irradiance is a site mean, never a sum. */
(function (root) {
  function selectRecords(plants, selection) {
    const selected = selection === 'all' ? plants : plants.filter((plant) => plant.id === selection);
    if (!selected.length) throw new Error('Unknown plant selection');
    const dates = selected[0].records.map((record) => record.date);
    const indexes = selected.map((plant) => new Map(plant.records.map((record) => [record.date, record])));
    if (indexes.some((index) => index.size !== dates.length || dates.some((date) => !index.has(date)))) {
      throw new Error('Plant date coverage must match before aggregation');
    }
    return dates.map((date) => {
      const rows = indexes.map((index) => index.get(date));
      return { date, measured: rows.reduce((sum, row) => sum + row.measured, 0),
        predicted: rows.reduce((sum, row) => sum + row.predicted, 0),
        forecastIrradiance: rows.reduce((sum, row) => sum + row.forecastIrradiance, 0) / rows.length };
    });
  }
  function rmse(records) {
    return Math.sqrt(records.reduce((sum, row) => sum + (row.predicted - row.measured) ** 2, 0) / records.length);
  }
  const helpers = { selectRecords, rmse };
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  else root.SolarDashboard = helpers;
})(typeof globalThis === 'undefined' ? this : globalThis);
