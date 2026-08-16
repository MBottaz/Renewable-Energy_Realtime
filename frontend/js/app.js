/* Renewable Energy Dashboard — static client (no modules, no network calls).
 * Production samples are 15-minute power values (MW). The production chart
 * displays hourly energy (MWh), using UTC hour buckets and a 0.25 h factor.
 */

'use strict';

// ── Pure helper: aggregate samples into hourly UTC buckets ───────────────
// Returns {labels, sums}, where sums are the raw sum of the samples in each
// hour. The browser applies the 0.25 h conversion when displaying energy.
function aggregateHourly(timestamps, values) {
  var buckets = new Map();
  for (var i = 0; i < timestamps.length; i++) {
    var t = new Date(timestamps[i]).getTime();
    if (values[i] == null) continue;
    var value = Number(values[i]);
    if (isNaN(t) || !isFinite(value)) continue;
    var key = Math.floor(t / 3600000) * 3600000;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(value);
  }

  var keys = Array.from(buckets.keys()).sort(function (a, b) { return a - b; });
  var pad = function (n) { return String(n).padStart(2, '0'); };
  var labels = keys.map(function (key) {
    var date = new Date(key);
    return date.getUTCFullYear() + '-' + pad(date.getUTCMonth() + 1) + '-' +
      pad(date.getUTCDate()) + 'T' + pad(date.getUTCHours()) + ':00';
  });
  var sums = keys.map(function (key) {
    return buckets.get(key).reduce(function (total, value) { return total + value; }, 0);
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
    var productionChart = null;
    var capacityChart = null;
    var scheduledPlot = false;

    var countrySelect = document.getElementById('country-select');
    var dateStart = document.getElementById('date-start');
    var dateEnd = document.getElementById('date-end');
    var statusEl = document.getElementById('status');
    var capacityGrid = document.getElementById('capacity-grid');
    var productionCaption = document.getElementById('chart-caption');
    var capacityCaption = document.getElementById('capacity-caption');
    var productionCanvas = document.getElementById('chart');
    var capacityCanvas = document.getElementById('capacity-chart');

    // Keep the browser palette aligned with core.config.PLOT_COLORS.
    // Technology families use related shades; orange is deliberately unused.
    var SOURCE_COLORS = {
      'Biomass': '#795548',
      'Geothermal': '#7E57C2',
      'Hydro Pumped Storage': '#1565C0',
      'Hydro Run-of-river and poundage': '#42A5F5',
      'Hydro Water Reservoir': '#0D47A1',
      'Other renewable': '#26A69A',
      'Solar': '#F4C430',
      'Wind Offshore': '#2E7D32',
      'Wind Onshore': '#66BB6A',
      'Energy storage': '#D32F2F',
      'Fossil Brown coal/Lignite': '#374151',
      'Fossil Coal-derived gas': '#4B5563',
      'Fossil Gas': '#6B7280',
      'Fossil Hard coal': '#52525B',
      'Fossil Oil': '#71717A',
      'Fossil Oil shale': '#9CA3AF',
      'Fossil Peat': '#A1A1AA',
      'Marine': '#00838F',
      'Nuclear': '#263238',
      'Waste': '#8D6E63',
      'Other': '#94A3B8'
    };
    var FALLBACK_COLORS = [
      '#42A5F5', '#66BB6A', '#F4C430', '#7E57C2', '#D32F2F', '#795548',
      '#64748B', '#00838F'
    ];

    function getSourceColor(name, index) {
      if (SOURCE_COLORS[name]) return SOURCE_COLORS[name];
      return FALLBACK_COLORS[(index || 0) % FALLBACK_COLORS.length];
    }

    function setStatus(message, isError) {
      statusEl.textContent = message || '';
      statusEl.className = isError ? 'error' : '';
    }

    function formatPower(value) {
      var number = Number(value) || 0;
      if (Math.abs(number) >= 1000) return (number / 1000).toFixed(2) + ' GW';
      return Math.round(number).toLocaleString('en-US') + ' MW';
    }

    function formatEnergy(value) {
      var number = Number(value) || 0;
      if (Math.abs(number) >= 1000) return (number / 1000).toFixed(2) + ' GWh';
      return Math.round(number).toLocaleString('en-US') + ' MWh';
    }

    function countryData(code) {
      return APP && APP.production ? APP.production[code] || null : null;
    }

    function availableDates(country) {
      var timestamps = country && country.timestamps || [];
      if (!timestamps.length) return { min: '', max: '' };
      return {
        min: timestamps[0].slice(0, 10),
        max: timestamps[timestamps.length - 1].slice(0, 10)
      };
    }

    function validDate(value, min, max) {
      return /^\d{4}-\d{2}-\d{2}$/.test(value || '') && value >= min && value <= max;
    }

    function setDateRange(country, range) {
      var dates = availableDates(country);
      dateStart.min = dates.min;
      dateStart.max = dates.max;
      dateEnd.min = dates.min;
      dateEnd.max = dates.max;
      dateStart.value = range && validDate(range.start, dates.min, dates.max) ? range.start : dates.min;
      dateEnd.value = range && validDate(range.end, dates.min, dates.max) ? range.end : dates.max;
    }

    function readUrlState() {
      var params = new URLSearchParams(window.location.search);
      return {
        country: params.get('country') || '',
        start: params.get('start') || '',
        end: params.get('end') || ''
      };
    }

    function writeUrlState(code, start, end) {
      if (!window.history || !window.history.replaceState) return;
      try {
        var url = new URL(window.location.href);
        url.searchParams.set('country', code);
        url.searchParams.set('start', start);
        url.searchParams.set('end', end);
        window.history.replaceState(null, '', url.href);
      } catch (error) {
        // The dashboard still works when opened directly as file://. URL
        // persistence is best-effort because some browsers restrict history
        // updates for local files.
      }
    }

    function schedulePlot() {
      if (scheduledPlot) return;
      scheduledPlot = true;
      window.requestAnimationFrame(function () {
        scheduledPlot = false;
        plot();
      });
    }

    function boot() {
      if (!APP || !APP.production || !Object.keys(APP.production).length) {
        setStatus('No data found. Run: python scripts/build.py', true);
        return;
      }

      var codes = Object.keys(APP.production);
      countrySelect.innerHTML = '';
      codes.forEach(function (code) {
        var option = document.createElement('option');
        option.value = code;
        option.textContent = code;
        countrySelect.appendChild(option);
      });

      var urlState = readUrlState();
      var initialCode = codes.indexOf(urlState.country) !== -1 ? urlState.country :
        (codes.indexOf('IT') !== -1 ? 'IT' : codes[0]);
      var initialCountry = countryData(initialCode);
      var initialDates = availableDates(initialCountry);
      var initialRange = {
        start: validDate(urlState.start, initialDates.min, initialDates.max) ? urlState.start : initialDates.min,
        end: validDate(urlState.end, initialDates.min, initialDates.max) ? urlState.end : initialDates.max
      };

      countrySelect.value = initialCode;
      setDateRange(initialCountry, initialRange);
      renderCapacity(initialCode);
      plot();

      countrySelect.addEventListener('change', function () {
        var country = countryData(countrySelect.value);
        setDateRange(country); // A new country starts at its complete range.
        renderCapacity(countrySelect.value);
        schedulePlot();
      });
      dateStart.addEventListener('input', schedulePlot);
      dateEnd.addEventListener('input', schedulePlot);
      dateStart.addEventListener('change', schedulePlot);
      dateEnd.addEventListener('change', schedulePlot);
    }

    function renderCapacity(code) {
      var cap = APP.capacity && APP.capacity[code];
      var entries = [];
      capacityGrid.innerHTML = '';

      if (cap && cap.sources) {
        entries = Object.keys(cap.sources).map(function (name) {
          return { name: name, value: Number(cap.sources[name]) || 0 };
        }).sort(function (a, b) { return b.value - a.value; });
      }

      if (!entries.length) {
        capacityCaption.textContent = 'No installed-capacity data available.';
        if (capacityChart) { capacityChart.destroy(); capacityChart = null; }
        return;
      }

      var positiveEntries = entries.filter(function (entry) { return entry.value > 0; });
      renderCapacityChart(positiveEntries);
      capacityCaption.textContent = 'All available technologies · ' +
        (cap.year ? 'reference year ' + cap.year : '');

      entries.forEach(function (entry, index) {
        var row = document.createElement('div');
        row.className = 'cap-row';
        var label = document.createElement('span');
        label.className = 'cap-name';
        label.textContent = entry.name;
        var value = document.createElement('span');
        value.className = 'cap-value';
        value.textContent = formatPower(entry.value);
        row.appendChild(label);
        row.appendChild(value);
        row.style.borderLeftColor = getSourceColor(entry.name, index);
        capacityGrid.appendChild(row);
      });

      var total = entries.reduce(function (sum, entry) { return sum + entry.value; }, 0);
      var totalRow = document.createElement('div');
      totalRow.className = 'cap-row cap-total';
      var totalLabel = document.createElement('span');
      totalLabel.className = 'cap-name';
      totalLabel.textContent = 'Total';
      var totalValue = document.createElement('span');
      totalValue.className = 'cap-value';
      totalValue.textContent = formatPower(total);
      totalRow.appendChild(totalLabel);
      totalRow.appendChild(totalValue);
      capacityGrid.appendChild(totalRow);
    }

    function renderCapacityChart(entries) {
      if (capacityChart) capacityChart.destroy();
      if (!entries.length) {
        capacityCaption.textContent = 'No non-zero installed-capacity values available.';
        return;
      }

      capacityChart = new Chart(capacityCanvas.getContext('2d'), {
        type: 'pie',
        data: {
          labels: entries.map(function (entry) { return entry.name; }),
          datasets: [{
            data: entries.map(function (entry) { return entry.value; }),
            backgroundColor: entries.map(function (entry, index) {
              return getSourceColor(entry.name, index);
            }),
            borderColor: '#ffffff',
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: { usePointStyle: true, padding: 12, boxWidth: 9, boxHeight: 9 }
            },
            tooltip: {
              callbacks: {
                label: function (context) {
                  return context.label + ': ' + formatPower(context.raw);
                }
              }
            }
          }
        }
      });
    }

    function plot() {
      var code = countrySelect.value;
      var start = dateStart.value;
      var end = dateEnd.value;
      var country = countryData(code);

      if (!country) { setStatus('Please choose a country.', true); return; }
      if (!start || !end) { setStatus('Please choose a date range.', true); return; }
      if (start > end) {
        setStatus('Start date must be before or equal to end date.', true);
        return;
      }

      var startTime = new Date(start + 'T00:00:00Z').getTime();
      var endTime = new Date(end + 'T23:59:59.999Z').getTime();
      var timestamps = [];
      var demand = [];
      var sourceValues = {};
      var sourceNames = Object.keys(country.sources || {});
      sourceNames.forEach(function (source) { sourceValues[source] = []; });

      for (var i = 0; i < country.timestamps.length; i++) {
        var time = new Date(country.timestamps[i]).getTime();
        if (time < startTime || time > endTime) continue;
        timestamps.push(country.timestamps[i]);
        demand.push(country.demand[i]);
        sourceNames.forEach(function (source) {
          sourceValues[source].push(country.sources[source][i]);
        });
      }

      if (!timestamps.length) {
        setStatus('No data points in the selected range.', true);
        return;
      }

      var demandHourly = aggregateHourly(timestamps, demand);
      var datasets = sourceNames.map(function (source, index) {
        var color = getSourceColor(source, index);
        return {
          label: source,
          data: aggregateHourly(timestamps, sourceValues[source]).sums.map(function (value) {
            return value * 0.25;
          }),
          borderColor: color,
          backgroundColor: hexToRgba(color, 0.58),
          borderWidth: 0.7,
          fill: true,
          tension: 0.1,
          pointRadius: 0,
          pointHoverRadius: 3,
          stack: 'production'
        };
      });

      datasets.push({
        label: 'Demand',
        data: demandHourly.sums.map(function (value) { return value * 0.25; }),
        type: 'line',
        stack: 'demand',
        borderColor: '#333333',
        backgroundColor: 'transparent',
        borderDash: [5, 5],
        borderWidth: 2,
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 3,
        order: 1
      });

      renderProductionChart(code, demandHourly.labels, datasets);
      writeUrlState(code, start, end);
      setStatus('Showing ' + demandHourly.labels.length + ' hourly points in UTC.');
    }

    function renderProductionChart(code, labels, datasets) {
      if (productionChart) productionChart.destroy();
      productionChart = new Chart(productionCanvas.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: {
              title: { display: true, text: 'Time (UTC)' },
              grid: { display: false },
              ticks: {
                maxRotation: 45,
                autoSkip: true,
                maxTicksLimit: 20,
                callback: function (value) {
                  var label = this.getLabelForValue(value);
                  return label.slice(5, 10) + ' ' + label.slice(11, 16);
                }
              }
            },
            y: {
              stacked: true,
              beginAtZero: true,
              title: { display: true, text: 'Hourly energy (MWh)' },
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
                label: function (context) {
                  return context.dataset.label + ': ' + formatEnergy(context.raw);
                }
              }
            },
            legend: {
              position: 'bottom',
              labels: { usePointStyle: true, padding: 14, boxWidth: 8, boxHeight: 8 }
            }
          }
        }
      });
      productionCaption.textContent = 'Country ' + code + ' · ' + dateStart.value +
        ' → ' + dateEnd.value + ' · hourly energy in MWh (UTC)';
    }

    function hexToRgba(hex, alpha) {
      var red = parseInt(hex.slice(1, 3), 16);
      var green = parseInt(hex.slice(3, 5), 16);
      var blue = parseInt(hex.slice(5, 7), 16);
      return 'rgba(' + red + ',' + green + ',' + blue + ',' + alpha + ')';
    }

    boot();
  }());
}
