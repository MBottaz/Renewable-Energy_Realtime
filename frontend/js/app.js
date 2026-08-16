/* Renewable Energy Dashboard — static client (no modules, no network calls).
 * Data comes from window.APP_DATA injected by js/data.js, so the page works by
 * opening index.html directly (file://).  Production series are 15-min power
 * samples (MW); the chart shows hourly energy (MWh) = raw sum of the ≤4
 * samples in each hour × 0.25 h (the ×0.25 conversion happens at display time).
 */

'use strict';

// ── Pure helper: aggregate 15-min samples into hourly buckets ──────────
// Returns {labels, sums}: one entry per hour bucket (UTC), labels[i] =
// "YYYY-MM-DDTHH:mm", sums[i] = RAW sum of the samples in that hour.
// Exported for node unit tests; the browser UI below is skipped under node.
function aggregateHourly(timestamps, values) {
  var buckets = new Map(); // hour key (epoch ms) -> [values]
  for (var i = 0; i < timestamps.length; i++) {
    var t = new Date(timestamps[i]).getTime();
    if (isNaN(t) || values[i] == null) continue;
    var key = Math.floor(t / 3600000) * 3600000;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(Number(values[i]));
  }
  var keys = Array.from(buckets.keys()).sort(function (a, b) { return a - b; });
  var pad = function (n) { return String(n).padStart(2, '0'); };
  var labels = keys.map(function (k) {
    var d = new Date(k);
    return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) +
      'T' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
  });
  var sums = keys.map(function (k) {
    return buckets.get(k).reduce(function (a, b) { return a + b; }, 0);
  });
  return { labels: labels, sums: sums };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { aggregateHourly: aggregateHourly };
}

// ── Browser UI (skipped under node for unit tests) ─────────────────────
if (typeof document !== 'undefined') {
  (function () {
    'use strict';

    var APP = window.APP_DATA || null;
    var chartInstance = null;

    // ── DOM refs ──
    var countrySelect = document.getElementById('country-select');
    var dateStart = document.getElementById('date-start');
    var dateEnd = document.getElementById('date-end');
    var plotBtn = document.getElementById('plot-btn');
    var statusEl = document.getElementById('status');
    var capacityGrid = document.getElementById('capacity-grid');
    var captionEl = document.getElementById('chart-caption');
    var canvas = document.getElementById('chart');

    // ── Colors (from core/config PLOT_COLORS) ──
    var SOURCE_COLORS = {
      'Biomass': '#8C564B',
      'Geothermal': '#D62728',
      'Hydro Pumped Storage': '#BCBD22',
      'Hydro Run-of-river and poundage': '#1F77B4',
      'Hydro Water Reservoir': '#17BECF',
      'Other renewable': '#E377C2',
      'Solar': '#FFBF00',
      'Wind Offshore': '#9467BD',
      'Wind Onshore': '#2CA02C',
      'Energy storage': '#7F7F7F',
      'Other': '#7F7F7F'
    };

    function getSourceColor(name) {
      return SOURCE_COLORS[name] || '#7F7F7F';
    }

    // ── Helpers ──
    function setStatus(msg, isError) {
      statusEl.textContent = msg || '';
      statusEl.style.color = isError ? '#dc2626' : '#666';
    }

    // Capacity values are in MW.
    function formatPower(value) {
      var v = Number(value) || 0;
      if (Math.abs(v) >= 1000) return (v / 1000).toFixed(2) + ' GW';
      return Math.round(v).toLocaleString('en-US') + ' MW';
    }

    // Chart values are hourly energy in MWh (15-min MW sums × 0.25 h).
    function formatEnergy(value) {
      var v = Number(value) || 0;
      if (Math.abs(v) >= 1000) return (v / 1000).toFixed(2) + ' GWh';
      return Math.round(v).toLocaleString('en-US') + ' MWh';
    }

    // ── 1. Boot ──
    function boot() {
      if (!APP || !APP.production || Object.keys(APP.production).length === 0) {
        setStatus('No data found. Run:  python scripts/build.py', true);
        return;
      }

      var codes = Object.keys(APP.production);
      countrySelect.innerHTML = '';
      codes.forEach(function (code) {
        var opt = document.createElement('option');
        opt.value = code;
        opt.textContent = code;
        countrySelect.appendChild(opt);
      });

      countrySelect.addEventListener('change', function () {
        selectCountry(countrySelect.value, true);
      });
      plotBtn.addEventListener('click', plot);

      selectCountry(codes[0], true);
    }

    function countryData(code) {
      return APP.production[code] || null;
    }

    function selectCountry(code, autoPlot) {
      var c = countryData(code);
      if (!c) return;

      // Available range comes from the timestamps themselves.
      var min = c.timestamps[0].slice(0, 10);
      var max = c.timestamps[c.timestamps.length - 1].slice(0, 10);
      dateStart.min = min;
      dateStart.max = max;
      dateEnd.min = min;
      dateEnd.max = max;
      dateStart.value = min;
      dateEnd.value = max;

      renderCapacity(code);
      if (autoPlot) plot();
    }

    // ── 2. Installed capacity (read-only panel) ──
    function renderCapacity(code) {
      var cap = APP.capacity[code];
      capacityGrid.innerHTML = '';
      if (!cap || !cap.sources) return;

      var entries = Object.keys(cap.sources)
        .map(function (name) { return { name: name, value: cap.sources[name] }; })
        .sort(function (a, b) { return b.value - a.value; });

      entries.forEach(function (e) {
        var row = document.createElement('div');
        row.className = 'cap-row';

        var label = document.createElement('span');
        label.className = 'cap-name';
        label.textContent = e.name;

        var val = document.createElement('span');
        val.className = 'cap-value';
        val.textContent = formatPower(e.value);

        row.appendChild(label);
        row.appendChild(val);
        capacityGrid.appendChild(row);
      });

      var total = entries.reduce(function (acc, e) { return acc + e.value; }, 0);
      var tRow = document.createElement('div');
      tRow.className = 'cap-row cap-total';
      var tLabel = document.createElement('span');
      tLabel.className = 'cap-name';
      tLabel.textContent = 'Total';
      var tVal = document.createElement('span');
      tVal.className = 'cap-value';
      tVal.textContent = formatPower(total);
      tRow.appendChild(tLabel);
      tRow.appendChild(tVal);
      capacityGrid.appendChild(tRow);
    }

    // ── 3. Plot ──
    function plot() {
      var code = countrySelect.value;
      var start = dateStart.value;
      var end = dateEnd.value;
      var c = countryData(code);

      if (!c) { setStatus('Please choose a country.', true); return; }
      if (!start || !end) { setStatus('Please choose a date range.', true); return; }
      if (start > end) { setStatus('Start date must be before end date.', true); return; }

      var startT = new Date(start + 'T00:00:00Z').getTime();
      var endT = new Date(end + 'T23:59:59Z').getTime();

      // Slice the 15-min series to the selected range.
      var ts = [];
      var dem = [];
      var srcVals = {};
      Object.keys(c.sources).forEach(function (s) { srcVals[s] = []; });
      for (var i = 0; i < c.timestamps.length; i++) {
        var t = new Date(c.timestamps[i]).getTime();
        if (t < startT || t > endT) continue;
        ts.push(c.timestamps[i]);
        dem.push(c.demand[i]);
        Object.keys(c.sources).forEach(function (s) { srcVals[s].push(c.sources[s][i]); });
      }

      if (ts.length === 0) {
        setStatus('No data points in the selected range.', true);
        return;
      }

      setStatus('Aggregating 15-min data to hourly energy…');
      var demandAgg = aggregateHourly(ts, dem);
      var labels = demandAgg.labels;

      var datasets = [];
      Object.keys(c.sources).forEach(function (s) {
        var color = getSourceColor(s);
        datasets.push({
          label: s,
          data: aggregateHourly(ts, srcVals[s]).sums.map(function (v) { return v * 0.25; }),
          borderColor: color,
          backgroundColor: hexToRgba(color, 0.6),
          fill: true,
          tension: 0.1,
          pointRadius: 0,
          pointHoverRadius: 3,
          borderWidth: 0.5
        });
      });

      datasets.push({
        label: 'Demand',
        data: demandAgg.sums.map(function (v) { return v * 0.25; }),
        type: 'line',
        stack: 'demand',
        borderColor: '#333',
        backgroundColor: 'transparent',
        borderDash: [5, 5],
        borderWidth: 2,
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 3,
        order: 1
      });

      renderChart(code, labels, datasets);
      setStatus('Showing ' + labels.length + ' hourly energy points (MWh).');
    }

    function renderChart(code, labels, datasets) {
      if (chartInstance) chartInstance.destroy();

      var ctx = canvas.getContext('2d');
      chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: {
              title: { display: true, text: 'Time' },
              grid: { display: false },
              ticks: {
                maxRotation: 45,
                autoSkip: true,
                maxTicksLimit: 20,
                callback: function (value) {
                  var l = this.getLabelForValue(value);
                  return l.slice(5, 10) + ' ' + l.slice(11); // MM-DD HH:mm
                }
              }
            },
            y: {
              stacked: true,
              title: { display: true, text: 'Energy (MWh)' },
              beginAtZero: true,
              ticks: {
                callback: function (value) {
                  return Math.abs(value) >= 1000 ? (value / 1000) + 'k' : value;
                }
              }
            }
          },
          plugins: {
            tooltip: {
              callbacks: {
                label: function (ctxObj) {
                  if (ctxObj.raw == null) return '';
                  return ctxObj.dataset.label + ': ' + formatEnergy(ctxObj.raw);
                }
              }
            },
            legend: {
              position: 'bottom',
              labels: { usePointStyle: true, padding: 16, boxWidth: 8, boxHeight: 8 }
            }
          }
        }
      });

      captionEl.textContent = 'Country ' + code + ' · ' + dateStart.value + ' → ' + dateEnd.value;
    }

    function hexToRgba(hex, alpha) {
      var r = parseInt(hex.slice(1, 3), 16);
      var g = parseInt(hex.slice(3, 5), 16);
      var b = parseInt(hex.slice(5, 7), 16);
      return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    // ── Go ──
    boot();
  })();
}
