/**
 * Energy Scenarios — Main Application
 *
 * Central pattern: appState holds all state, render() updates UI on every change.
 * Chart.js charts are updated with chart.data = ... + chart.update() (never recreated).
 */

/* ─── State ─── */
/** @type {AppState} */
const appState = {
  /** @type {Array<{ code: string, name: string, entsoe_key: string }>} */
  countries: [],
  /** @type {string[]} */
  selectedCountries: [],
  /** @type {Object<string, Object>} */
  rawCapacity: {},
  /** @type {Object<string, Object>} */
  rawGeneration: {},
  /** @type {Object<string, number>} */
  capacityScenario: {},
  /** @type {Object<string, number>} */
  capacityActual: {},
  /** @type {{ from: Date, to: Date }} */
  dateRange: null,
  /** @type {number} */
  selectedWeek: 52,
};

/* ─── Chart Instances ─── */
/** @type {Chart|null} */
let durationChart = null;
/** @type {Chart|null} */
let weeklyChart = null;

/* ─── Constants ─── */
const RENEWABLE_SOURCES = ["Solar", "Wind Onshore", "Wind Offshore", "Hydro"];
const DISPATCHABLE_SOURCES = ["Gas", "Coal", "Other"];
const ALL_SOURCES = [...RENEWABLE_SOURCES, ...DISPATCHABLE_SOURCES];
const NUCLEAR_SOURCES = ["Nuclear"];

const SOURCE_COLORS = {
  "Solar": "#f5c842",
  "Wind Onshore": "#5bc0de",
  "Wind Offshore": "#3a8ebd",
  "Hydro": "#3178c6",
  "Nuclear": "#9b59b6",
  "Gas": "#e67e22",
  "Coal": "#7f8c8d",
  "Other": "#bdc3c7",
};

/* ─── Data Loading ─── */

/**
 * Load countries.json and all capacity/generation files.
 * @returns {Promise<void>}
 */
async function loadAllData() {
  try {
    // Load countries
    const countriesRes = await fetch("data/countries.json");
    appState.countries = await countriesRes.json();
    renderCountrySelector();

    // Load capacity & generation for each country
    const promises = appState.countries.map(async (c) => {
      const [capRes, genRes] = await Promise.allSettled([
        fetch(`data/capacity_${c.code}.json`),
        fetch(`data/generation_${c.code}_2024.json`),
      ]);

      if (capRes.status === "fulfilled") {
        appState.rawCapacity[c.code] = await capRes.value.json();
      }
      if (genRes.status === "fulfilled") {
        appState.rawGeneration[c.code] = await genRes.value.json();
      }
    });

    await Promise.all(promises);
    console.log("Dati caricati:", {
      countries: appState.countries.length,
      capacities: Object.keys(appState.rawCapacity).length,
      generations: Object.keys(appState.rawGeneration).length,
    });
  } catch (err) {
    console.error("Errore caricamento dati:", err);
  }
}

/* ─── Country Selector ─── */

/** Render country toggle buttons. */
function renderCountrySelector() {
  const container = document.getElementById("country-selector");
  container.textContent = "";

  appState.countries.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "country-btn";
    if (appState.selectedCountries.includes(c.code)) {
      btn.classList.add("selected");
    }
    btn.textContent = c.name;
    btn.addEventListener("click", () => toggleCountry(c.code));
    container.appendChild(btn);
  });
}

/**
 * Toggle a country in the selection.
 * @param {string} code
 */
function toggleCountry(code) {
  const idx = appState.selectedCountries.indexOf(code);
  if (idx >= 0) {
    appState.selectedCountries.splice(idx, 1);
  } else {
    appState.selectedCountries.push(code);
  }
  onStateChange();
}

/* ─── State Change Handler ─── */

/** Called whenever appState changes — recalculates scaled data and calls render(). */
function onStateChange() {
  recalculateScenario();
  render();
}

/* ─── Scenario Calculation ─── */

/** Accumulate capacity and generation for selected countries, apply scenario scaling. */
function recalculateScenario() {
  const selected = appState.selectedCountries;
  if (selected.length === 0) {
    appState.capacityActual = {};
    appState.capacityScenario = {};
    appState.scaledData = null;
    appState.dateRange = null;
    return;
  }

  // Accumulate capacities
  /** @type {Object<string, number>} */
  const totalActual = {};
  /** @type {Object<string, number>} */
  const totalScenario = {};
  let oldestUpdated = null;

  selected.forEach((code) => {
    const cap = appState.rawCapacity[code];
    if (!cap) return;

    if (cap.updated && (!oldestUpdated || cap.updated < oldestUpdated)) {
      oldestUpdated = cap.updated;
    }

    for (const [source, value] of Object.entries(cap.sources || {})) {
      totalActual[source] = (totalActual[source] || 0) + value;
      totalScenario[source] = (totalScenario[source] || 0) + value;
    }
  });

  appState.capacityActual = totalActual;
  appState.capacityScenario = { ...totalScenario };
  appState.oldestUpdated = oldestUpdated;

  // Accumulate generation data (element-wise sum)
  /** @type {Object<string, number[]>|null} */
  let sumLoad = null;
  /** @type {Object<string, number[]>} */
  const sumGen = {};
  let maxHours = 0;

  selected.forEach((code) => {
    const gen = appState.rawGeneration[code];
    if (!gen) return;

    if (!sumLoad) {
      sumLoad = gen.load.slice();
      maxHours = gen.load.length;
    } else {
      for (let i = 0; i < Math.min(maxHours, gen.load.length); i++) {
        sumLoad[i] += gen.load[i] || 0;
      }
    }

    for (const src of gen.sources || []) {
      if (!sumGen[src]) sumGen[src] = new Array(maxHours).fill(0);
      const arr = gen.generation[src];
      if (arr) {
        for (let i = 0; i < Math.min(maxHours, arr.length); i++) {
          sumGen[src][i] = (sumGen[src][i] || 0) + (arr[i] || 0);
        }
      }
    }
  });

  if (!sumLoad) {
    appState.scaledData = null;
    appState.dateRange = null;
    return;
  }

  // Apply scenario scaling
  /** @type {Object<string, number[]>} */
  const scaledGen = {};
  for (const src of ALL_SOURCES) {
    const origArr = sumGen[src];
    if (!origArr) {
      scaledGen[src] = new Array(maxHours).fill(0);
      continue;
    }
    const actual = appState.capacityActual[src] || 1;
    const scenario = appState.capacityScenario[src] || actual;
    const factor = actual > 0 ? scenario / actual : 1;
    scaledGen[src] = origArr.map((v) => v * factor);
  }

  appState.scaledData = {
    load: sumLoad,
    generation: scaledGen,
    hours: maxHours,
  };

  // Set default date range: full year
  const start = new Date(Date.UTC(2024, 0, 1, 0, 0, 0));
  const end = new Date(Date.UTC(2024, 11, 31, 23, 0, 0));
  if (!appState.dateRange) {
    appState.dateRange = { from: start, to: end };
  }
  // Clamp dateRange to data bounds
  const dataStart = new Date(Date.UTC(2024, 0, 1, 0, 0, 0));
  const dataEnd = new Date(Date.UTC(2024, 11, 31, 23, 0, 0));
  if (appState.dateRange.from < dataStart) appState.dateRange.from = dataStart;
  if (appState.dateRange.to > dataEnd) appState.dateRange.to = dataEnd;
}

/* ─── Render ─── */

/**
 * Main render function: updates all UI elements from appState.
 * Called after every state change.
 */
function render() {
  renderCountrySelector();
  renderCapacityTable();
  renderDateControls();
  renderKPI();
  renderDurationCurve();
  renderWeeklyChart();
}

/* ─── Capacity Table ─── */

/** Render the capacity table with scenario inputs. */
function renderCapacityTable() {
  const tbody = document.getElementById("capacity-tbody");
  const updatedEl = document.getElementById("capacity-updated");

  const actual = appState.capacityActual;
  const scenario = appState.capacityScenario;

  if (Object.keys(actual).length === 0) {
    tbody.textContent = "";
    updatedEl.textContent = "";
    return;
  }

  if (appState.oldestUpdated) {
    updatedEl.textContent = `Ultimo aggiornamento dati: ${appState.oldestUpdated}`;
  }

  tbody.textContent = "";

  const sources = Object.keys(actual).sort();
  sources.forEach((src) => {
    const tr = document.createElement("tr");

    // Source name
    const tdName = document.createElement("td");
    tdName.textContent = src;
    tr.appendChild(tdName);

    // Actual capacity
    const tdActual = document.createElement("td");
    tdActual.textContent = actual[src].toLocaleString();
    tr.appendChild(tdActual);

    // Scenario input
    const tdScenario = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.value = (scenario[src] || actual[src]).toString();
    input.min = 0;
    input.step = 100;
    input.addEventListener("input", () => {
      const val = parseFloat(input.value);
      if (!isNaN(val) && val >= 0) {
        appState.capacityScenario[src] = val;
        onStateChange();
      }
    });
    tdScenario.appendChild(input);
    tr.appendChild(tdScenario);

    // Reset button
    const tdReset = document.createElement("td");
    const resetBtn = document.createElement("button");
    resetBtn.className = "reset-btn";
    resetBtn.textContent = "←";
    resetBtn.title = `Ripristina ${actual[src].toLocaleString()} MW`;
    resetBtn.addEventListener("click", () => {
      appState.capacityScenario[src] = actual[src];
      onStateChange();
    });
    tdReset.appendChild(resetBtn);
    tr.appendChild(tdReset);

    tbody.appendChild(tr);
  });
}

/* ─── Date Controls ─── */

/** Render date inputs and wire events. */
function renderDateControls() {
  const fromEl = document.getElementById("date-from");
  const toEl = document.getElementById("date-to");

  if (!appState.scaledData) return;

  const fmt = (d) => d.toISOString().slice(0, 10);
  if (!fromEl.value && !toEl.value) {
    fromEl.value = fmt(appState.dateRange.from);
    toEl.value = fmt(appState.dateRange.to);
    fromEl.min = fmt(new Date(Date.UTC(2024, 0, 1)));
    fromEl.max = fmt(new Date(Date.UTC(2024, 11, 31)));
    toEl.min = fmt(new Date(Date.UTC(2024, 0, 1)));
    toEl.max = fmt(new Date(Date.UTC(2024, 11, 31)));
  }

  // Remove old listeners by cloning
  const newFrom = fromEl.cloneNode(true);
  const newTo = toEl.cloneNode(true);
  fromEl.parentNode.replaceChild(newFrom, fromEl);
  toEl.parentNode.replaceChild(newTo, toEl);

  newFrom.addEventListener("change", () => {
    appState.dateRange.from = new Date(newFrom.value + "T00:00:00Z");
    renderKPI();
    renderDurationCurve();
    renderWeeklyChart();
  });

  newTo.addEventListener("change", () => {
    appState.dateRange.to = new Date(newTo.value + "T23:00:00Z");
    renderKPI();
    renderDurationCurve();
    renderWeeklyChart();
  });

  // Week slider
  const slider = document.getElementById("week-slider");
  const weekLabel = document.getElementById("week-label");
  if (slider && appState.selectedWeek) {
    slider.value = appState.selectedWeek;
    weekLabel.textContent = appState.selectedWeek;

    slider.oninput = () => {
      appState.selectedWeek = parseInt(slider.value);
      weekLabel.textContent = appState.selectedWeek;
      renderWeeklyChart();
    };
  }
}

/* ─── KPI ─── */

/** Compute and display the three KPI cards. */
function renderKPI() {
  const sd = appState.scaledData;
  if (!sd || !appState.dateRange) {
    document.getElementById("kpi-surplus").textContent = "—";
    document.getElementById("kpi-deficit").textContent = "—";
    document.getElementById("kpi-renewable").textContent = "—";
    return;
  }

  const fromHour = hourIndex(appState.dateRange.from);
  const toHour = hourIndex(appState.dateRange.to);

  let surplusHours = 0;
  let deficitHours = 0;
  let totalRenEnergy = 0;
  let totalEnergy = 0;

  for (let h = fromHour; h <= toHour && h < sd.hours; h++) {
    const renew = RENEWABLE_SOURCES.reduce(
      (sum, src) => sum + (sd.generation[src]?.[h] || 0),
      0
    );
    const load = sd.load[h];
    totalRenEnergy += renew;
    totalEnergy += load;

    if (renew >= load) {
      surplusHours++;
    } else {
      deficitHours++;
    }
  }

  const renPct = totalEnergy > 0 ? (totalRenEnergy / totalEnergy) * 100 : 0;

  document.getElementById("kpi-surplus").textContent = surplusHours.toLocaleString();
  document.getElementById("kpi-deficit").textContent = deficitHours.toLocaleString();
  document.getElementById("kpi-renewable").textContent = `${renPct.toFixed(1)}%`;
}

/**
 * Convert a Date to hour index (0-based from Jan 1 2024 00:00 UTC).
 * @param {Date} date
 * @returns {number}
 */
function hourIndex(date) {
  const start = new Date(Date.UTC(2024, 0, 1, 0, 0, 0));
  return Math.floor((date.getTime() - start.getTime()) / 3600000);
}

/* ─── Duration Curve ─── */

/** Render or update the duration curve chart. */
function renderDurationCurve() {
  const sd = appState.scaledData;
  if (!sd || !appState.dateRange) return;

  const fromHour = hourIndex(appState.dateRange.from);
  const toHour = hourIndex(appState.dateRange.to);
  const ctx = document.getElementById("duration-chart").getContext("2d");

  // Calculate surplus values for each hour in range
  /** @type {number[]} */
  const surplus = [];
  for (let h = fromHour; h <= toHour && h < sd.hours; h++) {
    const renew = RENEWABLE_SOURCES.reduce(
      (sum, src) => sum + (sd.generation[src]?.[h] || 0),
      0
    );
    surplus.push(renew - sd.load[h]);
  }
  surplus.sort((a, b) => b - a);

  const n = surplus.length;
  const surplusOnly = surplus.map((v) => (v >= 0 ? v : NaN));
  const deficitOnly = surplus.map((v) => (v < 0 ? v : NaN));

  if (!durationChart) {
    durationChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: surplus.map((_, i) => i.toString()),
        datasets: [
          {
            label: "Surplus",
            data: surplusOnly,
            backgroundColor: "rgba(46, 204, 113, 0.3)",
            borderColor: "rgba(46, 204, 113, 0.8)",
            borderWidth: 1.5,
            fill: true,
            pointRadius: 0,
            tension: 0.1,
          },
          {
            label: "Deficit",
            data: deficitOnly,
            backgroundColor: "rgba(230, 126, 34, 0.3)",
            borderColor: "rgba(230, 126, 34, 0.8)",
            borderWidth: 1.5,
            fill: true,
            pointRadius: 0,
            tension: 0.1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${Math.round(ctx.parsed.y).toLocaleString()} MW`,
              afterBody: () => {
                const surplusCount = surplus.filter((v) => v >= 0).length;
                const deficitCount = surplus.filter((v) => v < 0).length;
                return `Ore in surplus: ${surplusCount}\nOre in deficit: ${deficitCount}`;
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "Ore (ordinate decrescenti)" },
          },
          y: {
            title: { display: true, text: "Surplus (MW)" },
          },
        },
      },
    });
  } else {
    durationChart.data.labels = surplus.map((_, i) => i.toString());
    durationChart.data.datasets[0].data = surplusOnly;
    durationChart.data.datasets[1].data = deficitOnly;
    durationChart.update();
  }
}

/* ─── Weekly Chart ─── */

/** Render or update the weekly stacked area chart. */
function renderWeeklyChart() {
  const sd = appState.scaledData;
  if (!sd || !appState.dateRange) return;

  const fromHour = hourIndex(appState.dateRange.from);
  const totalHours = appState.dateRange.to
    ? hourIndex(appState.dateRange.to) - fromHour + 1
    : sd.hours - fromHour;

  const totalWeeks = Math.max(1, Math.floor(totalHours / 168));
  const week = Math.min(appState.selectedWeek, totalWeeks) - 1;
  const startHour = fromHour + week * 168;
  const nHours = Math.min(168, sd.hours - startHour);

  // Build datasets
  const labels = [];
  for (let i = 0; i < nHours; i++) {
    const d = new Date(Date.UTC(2024, 0, 1, 0, 0, 0) + (startHour + i) * 3600000);
    labels.push(d.toLocaleDateString("it", { weekday: "short", hour: "2-digit" }));
  }

  // Generation sources for stacking (renewables + dispatchable, no Nuclear in stacked area)
  const stackSources = [...RENEWABLE_SOURCES, ...DISPATCHABLE_SOURCES];
  const loadData = [];
  for (let i = 0; i < nHours; i++) {
    loadData.push((sd.load[startHour + i] || 0) / 1000); // Convert to GW
  }

  const ctx = document.getElementById("weekly-chart").getContext("2d");

  if (!weeklyChart) {
    const datasets = stackSources.map((src) => ({
      label: src,
      data: [],
      backgroundColor: SOURCE_COLORS[src] || "#95a5a6",
      borderColor: SOURCE_COLORS[src] || "#95a5a6",
      borderWidth: 0,
      fill: true,
    }));

    // Add load line dataset
    datasets.push({
      label: "Carico",
      data: [],
      borderColor: "#000000",
      backgroundColor: "transparent",
      borderWidth: 2,
      fill: false,
      pointRadius: 0,
      type: "line",
      order: 0,
    });

    weeklyChart = new Chart(ctx, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
        },
        scales: {
          x: {
            title: { display: true, text: "Giorno e Ora" },
            ticks: { maxTicksLimit: 20 },
          },
          y: {
            stacked: true,
            title: { display: true, text: "GW" },
            beginAtZero: true,
          },
        },
      },
    });
  }

  // Update data
  weeklyChart.data.labels = labels;

  for (let si = 0; si < stackSources.length; si++) {
    const src = stackSources[si];
    const arr = [];
    for (let i = 0; i < nHours; i++) {
      arr.push((sd.generation[src]?.[startHour + i] || 0) / 1000);
    }
    weeklyChart.data.datasets[si].data = arr;
  }

  // Update load line (last dataset)
  const loadDs = weeklyChart.data.datasets[stackSources.length];
  if (loadDs) {
    loadDs.data = loadData;
  }

  weeklyChart.update();
}

/* ─── Init ─── */

/**
 * Initialize the application.
 * Loads data, sets up default state, and calls render().
 */
async function init() {
  await loadAllData();
  if (appState.countries.length > 0) {
    // Default: select IT and DE
    toggleCountry("IT");
    toggleCountry("DE");
  }
  render();
}

document.addEventListener("DOMContentLoaded", init);