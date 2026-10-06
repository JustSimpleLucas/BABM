/* Client for the BABM market-statistics dashboard.
 *
 * The browser holds no analysis logic. Every statistic on the page is computed
 * server-side by `abm_analysis.statistics`, so a number read here is the same
 * number the exported CSV tables hold. This file selects a run, formats the
 * payload, and draws the charts.
 *
 * Statistics are reported per traded asset. The payload always carries at least
 * one asset name, so tables and charts have a single code path: a single-asset
 * run is the one-column case, not a special case.
 */

'use strict';

const state = {
  catalogue: null,
  selectedPath: null,
  phase: 'simulation',
  priceColumn: 'market_price',
  filterText: '',
  view: null,
  priceScale: 'level',
  // Window, in steps, of the moving average drawn over the price; 0 draws the raw
  // price alone. Like the hidden rows it is kept across runs, and falls back to 0
  // when a run does not offer the window (a short run, say).
  priceSmoothing: 0,
  // Which moving average is drawn (the payload's own key for it) and whether the
  // raw price stays beneath it. Kept across runs, like the window.
  priceSmoothingMethod: 'simple',
  showRawPrice: true,
  acfSeries: 'all',
  // Cohort mode. `selectedPaths` is the tick-box selection, which is kept
  // independent of `selectedPath`: ticking runs to compare should not move the
  // single-run page out from under the reader.
  mode: 'run',
  selectedPaths: new Set(),
  cohort: null,
  cohortAsset: null,
  convergenceMetric: null,
  spreadMetric: null,
  // Incremented on every fetch so a slow reply that lands after a newer one is
  // discarded rather than drawn over the run the reader is now looking at.
  requestGeneration: 0,
  // Whether the four chartist rules are drawn as one family or kept apart. It is
  // one switch for every per-strategy view, so the stack, the matrix and the
  // wealth densities always agree about what a "strategy" is.
  strategyGrouping: 'family',
  // How stress is defined, which market the stack shades, and which stack rows
  // the reader has hidden. The last is kept across runs so a chosen view survives.
  stressDefinition: 'volatility',
  focusAsset: null,
  hiddenRows: new Set(),
  flowMatrixMode: 'share',
  mapColour: 'opinion',
  // Cohort fan chart.
  pathMeasure: null,
  showMembers: false,
  // Calibration mode.
  studies: [],
  selectedStudy: null,
  calibration: null,
  decompositionOrder: 'trial',
};

const elements = {
  archiveRoot: document.getElementById('archive-root'),
  phaseSelect: document.getElementById('phase-select'),
  priceColumnSelect: document.getElementById('price-column-select'),
  runSearch: document.getElementById('run-search'),
  runList: document.getElementById('run-list'),
  sidebarCount: document.getElementById('sidebar-count'),
  placeholder: document.getElementById('placeholder'),
  runView: document.getElementById('run-view'),
  status: document.getElementById('status'),
  runId: document.getElementById('run-id'),
  runProvenance: document.getElementById('run-provenance'),
  runParameters: document.getElementById('run-parameters'),
  assetLegend: document.getElementById('asset-legend'),
  factGrid: document.getElementById('fact-grid'),
  metricSections: document.getElementById('metric-sections'),
  crossAssetPanel: document.getElementById('cross-asset-panel'),
  crossAssetMetrics: document.getElementById('cross-asset-metrics'),
  agentMetrics: document.getElementById('agent-metrics'),
  agentTable: document.getElementById('agent-table'),
  agentMessage: document.getElementById('agent-message'),
  protagonistIdentity: document.getElementById('protagonist-identity'),
  protagonistMetrics: document.getElementById('protagonist-metrics'),
  protagonistMessage: document.getElementById('protagonist-message'),
  priceScale: document.getElementById('price-scale'),
  priceSmoothing: document.getElementById('price-smoothing'),
  priceSmoothingMethod: document.getElementById('price-smoothing-method'),
  rawPriceToggle: document.getElementById('raw-price-toggle'),
  smoothingNote: document.getElementById('smoothing-note'),
  acfSeries: document.getElementById('acf-series'),
  runFooter: document.getElementById('run-footer'),
  cohortBar: document.getElementById('cohort-bar'),
  cohortBarCount: document.getElementById('cohort-bar-count'),
  cohortClear: document.getElementById('cohort-clear'),
  cohortCompare: document.getElementById('cohort-compare'),
  cohortView: document.getElementById('cohort-view'),
  cohortTitle: document.getElementById('cohort-title'),
  cohortSummary: document.getElementById('cohort-summary'),
  conditionLegend: document.getElementById('condition-legend'),
  cohortAssetLegend: document.getElementById('cohort-asset-legend'),
  cohortAsset: document.getElementById('cohort-asset'),
  verdictSummary: document.getElementById('verdict-summary'),
  verdictTable: document.getElementById('verdict-table'),
  verdictMessage: document.getElementById('verdict-message'),
  cohortFactGrid: document.getElementById('cohort-fact-grid'),
  cohortMetricSections: document.getElementById('cohort-metric-sections'),
  convergenceMetric: document.getElementById('convergence-metric'),
  convergenceMessage: document.getElementById('convergence-message'),
  spreadMetric: document.getElementById('spread-metric'),
  spreadMessage: document.getElementById('spread-message'),
  cohortDistributionMessage: document.getElementById('cohort-distribution-message'),
  cohortFooter: document.getElementById('cohort-footer'),
  strategyGrouping: document.getElementById('strategy-grouping'),
  studyList: document.getElementById('study-list'),
  stressDefinition: document.getElementById('stress-definition'),
  focusAsset: document.getElementById('focus-asset'),
  rowToggles: document.getElementById('row-toggles'),
  stackMessage: document.getElementById('stack-message'),
  stackRule: document.getElementById('stack-rule'),
  stressTable: document.getElementById('stress-table'),
  flowPanel: document.getElementById('flow-panel'),
  flowMatrixMode: document.getElementById('flow-matrix-mode'),
  flowMessage: document.getElementById('flow-message'),
  agentMap: document.getElementById('agent-map'),
  mapColour: document.getElementById('map-colour'),
  socialMapMessage: document.getElementById('social-map-message'),
  pathMeasure: document.getElementById('path-measure'),
  pathMembers: document.getElementById('path-members'),
  pathsMessage: document.getElementById('paths-message'),
  calibrationView: document.getElementById('calibration-view'),
  calibrationTitle: document.getElementById('calibration-title'),
  calibrationChips: document.getElementById('calibration-chips'),
  calibrationMetrics: document.getElementById('calibration-metrics'),
  calibrationProgressMessage: document.getElementById('calibration-progress-message'),
  decompositionOrder: document.getElementById('decomposition-order'),
  calibrationDecompositionMessage: document.getElementById('calibration-decomposition-message'),
  calibrationLevels: document.getElementById('calibration-levels'),
  calibrationParameters: document.getElementById('calibration-parameters'),
  calibrationParametersMessage: document.getElementById('calibration-parameters-message'),
  calibrationCandidates: document.getElementById('calibration-candidates'),
  calibrationValidationMessage: document.getElementById('calibration-validation-message'),
  calibrationFooter: document.getElementById('calibration-footer'),
};

/* ------------------------------------------------------------ formatting */

/** Format one value according to the format hint the server attached. */
function formatValue(value, format) {
  if (value === null || value === undefined) {
    return '—';
  }
  switch (format) {
    case 'integer':
      return Math.round(value).toLocaleString('en-GB');
    case 'amount':
      return Math.abs(value) >= 1000
        ? value.toLocaleString('en-GB', { maximumFractionDigits: 0 })
        : value.toFixed(2);
    case 'p_value':
      if (value < 0.001) return '< 0.001';
      if (value > 0.999) return '> 0.999';
      return value.toFixed(3);
    case 'price':
      return value.toFixed(2);
    case 'percent_points':
      return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
    case 'percent_fraction':
      return `${(value * 100).toFixed(2)}%`;
    case 'scientific':
      if (value === 0) return '0';
      return Math.abs(value) < 0.001 ? value.toExponential(3) : value.toFixed(5);
    case 'flag':
      return value ? 'Yes' : 'No';
    case 'decimal':
    default:
      return Math.abs(value) >= 1000 ? value.toFixed(1) : value.toFixed(4);
  }
}

/** Format a parameter chip's value, keeping switches readable as on/off. */
function formatParameter(parameter) {
  if (parameter.value === null || parameter.value === undefined) {
    return '—';
  }
  if (parameter.kind === 'switch') {
    return parameter.value ? 'on' : 'off';
  }
  if (parameter.kind === 'rate') {
    return `${(parameter.value * 100).toFixed(3)}%`;
  }
  if (parameter.kind === 'decimal') {
    return parameter.value.toFixed(4);
  }
  return Number(parameter.value).toLocaleString('en-GB');
}

/** Shorten a filesystem path to its last few components for the header.
 *
 * The full path stays available as the element's tooltip; research archives
 * routinely live several directories deep and the tail is the informative part.
 */
function shortenPath(path, keep) {
  const parts = String(path).split('/').filter(Boolean);
  const tail = parts.slice(-(keep || 3));
  return (tail.length < parts.length ? '…/' : '/') + tail.join('/');
}

/** Read one CSS custom property so charts follow the page's colour scheme. */
function cssValue(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Return the colour reserved for the nth asset, wrapping past the fourth. */
/** Number of distinct asset colours the stylesheet defines. */
const ASSET_COLOUR_COUNT = 6;

/** Number of distinct condition colours the stylesheet defines. */
const CONDITION_COLOUR_COUNT = 6;

/** Return the colour keying one traded market.
 *
 * Past the end of the ramp the series is drawn in a neutral tone rather than
 * wrapping back to the first colour. Wrapping would put two markets under one
 * key and silently attribute one market's line to the other; an unkeyed grey
 * line is wrong in a way the reader can see.
 */
function assetColour(index) {
  return index < ASSET_COLOUR_COUNT
    ? cssValue(`--asset-${index + 1}`)
    : cssValue('--text-faint');
}

/** Return the colour keying one experimental condition, on the same terms. */
function conditionColour(index) {
  return index < CONDITION_COLOUR_COUNT
    ? cssValue(`--condition-${index + 1}`)
    : cssValue('--text-faint');
}

/** Render a condition's colour dot for the legend and table headers. */
function conditionSwatch(index) {
  return `<span class="condition-swatch" style="background:${conditionColour(index)}"></span>`;
}

function escapeHtml(text) {
  const node = document.createElement('div');
  node.textContent = text === null || text === undefined ? '' : String(text);
  return node.innerHTML;
}

/** Render an asset's colour dot, so tables, legend, and charts share a key. */
function swatch(index) {
  return `<span class="asset-swatch" style="background:${assetColour(index)}"></span>`;
}

/* -------------------------------------------------------- strategy colours */

/** Stylesheet token holding each strategy family's colour. */
const STRATEGY_COLOUR_TOKENS = {
  fundamentalist: '--strategy-fundamentalist',
  chartist: '--strategy-chartist',
  noise_trader: '--strategy-noise',
  buy_and_hold: '--strategy-buy-and-hold',
};

/** Line dash for the nth rule of a family, so rules that share a hue stay apart. */
const VARIANT_DASHES = ['solid', 'dash', 'dot', 'dashdot'];

/** Marker symbol for each family, for maps where hue is spent on a quantity. */
const FAMILY_SYMBOLS = {
  fundamentalist: 'circle',
  chartist: 'square',
  noise_trader: 'diamond',
  buy_and_hold: 'triangle-up',
};

/** Make a strategy label readable: `chartist_mean_reversion` → "chartist mean reversion". */
function prettyStrategy(label) {
  return String(label).replace(/_/g, ' ');
}

/**
 * Return how each strategy group is drawn.
 *
 * Colour follows the *family*, never the group's place in a list: a strategy that
 * was blue in one run is blue in every run, whatever mix of agents the run holds.
 * Rules of one family share its hue and are told apart by dash and opacity, so
 * splitting the chartists never repaints anything else.
 *
 * @param {string[]} groups the groups drawn, in display order
 * @param {(group: string) => string} familyOf the family a group belongs to
 */
function strategyStyles(groups, familyOf) {
  const sizes = {};
  groups.forEach((group) => {
    const family = familyOf(group);
    sizes[family] = (sizes[family] || 0) + 1;
  });
  const placed = {};
  const styles = {};
  groups.forEach((group) => {
    const family = familyOf(group);
    const index = placed[family] || 0;
    placed[family] = index + 1;
    const token = STRATEGY_COLOUR_TOKENS[family];
    const split = sizes[family] > 1;
    styles[group] = {
      colour: token ? cssValue(token) : cssValue('--text-faint'),
      dash: split ? VARIANT_DASHES[index % VARIANT_DASHES.length] : 'solid',
      opacity: split ? Math.max(0.45, 1 - 0.18 * index) : 1,
      symbol: FAMILY_SYMBOLS[family] || 'circle',
    };
  });
  return styles;
}

/** Plotly colourscale for a magnitude: the page surface to the accent, one hue. */
function sequentialScale() {
  return [
    [0, cssValue('--surface')],
    [1, cssValue('--accent')],
  ];
}

/** Plotly colourscale for a signed quantity: cool pole, neutral midpoint, warm pole. */
function divergingScale() {
  return [
    [0, cssValue('--polarity-negative')],
    [0.5, cssValue('--surface-muted')],
    [1, cssValue('--polarity-positive')],
  ];
}

/* ------------------------------------------------ table view and CSV twins */

//: Rows a table view shows; the CSV always carries every row.
const TWIN_ROW_LIMIT = 400;

/** The numbers behind each chart that has a twin, by chart id. */
const twinTables = new Map();

function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function twinCsv(table) {
  const lines = [table.columns.map(csvCell).join(',')];
  table.rows.forEach((row) => lines.push(row.map(csvCell).join(',')));
  return `${lines.join('\n')}\n`;
}

/** Fill a twin's table view from the numbers a chart plots. */
function renderTwinTable(chartId) {
  const table = twinTables.get(chartId);
  const container = document.getElementById(`${chartId}-twin-table`);
  if (!table || !container) return;
  const head = table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('');
  const shown = table.rows.slice(0, TWIN_ROW_LIMIT);
  const body = shown
    .map(
      (row) =>
        `<tr>${row
          .map((cell) => {
            const text =
              typeof cell === 'number'
                ? Math.abs(cell) >= 1000 || (cell !== 0 && Math.abs(cell) < 0.001)
                  ? cell.toPrecision(5)
                  : String(Math.round(cell * 1e6) / 1e6)
                : cell === null || cell === undefined
                  ? '—'
                  : String(cell);
            return `<td class="metric-number${cell === null ? ' is-missing' : ''}">${escapeHtml(text)}</td>`;
          })
          .join('')}</tr>`
    )
    .join('');
  const note =
    table.rows.length > shown.length
      ? `<div class="twin-note">Showing the first ${TWIN_ROW_LIMIT.toLocaleString('en-GB')} of ` +
        `${table.rows.length.toLocaleString('en-GB')} rows; the CSV holds all of them.</div>`
      : '';
  container.innerHTML =
    `<div class="table-scroll"><table class="metric-table"><thead><tr>${head}</tr></thead>` +
    `<tbody>${body}</tbody></table></div>${note}`;
}

/** Download a twin's full table as a CSV, entirely in the browser. */
function downloadTwin(chartId) {
  const table = twinTables.get(chartId);
  if (!table) return;
  const url = URL.createObjectURL(new Blob([twinCsv(table)], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${table.name}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Offer a table view and a CSV download of the numbers a chart plots.
 *
 * A tooltip must never be the only way to read a value, and the series behind a
 * figure should be citable as numbers rather than as a picture of them. The bar
 * is created once beside the chart and reused on every redraw.
 */
function setTwin(chartId, name, table) {
  twinTables.set(chartId, { name, ...table });
  const chart = document.getElementById(chartId);
  let bar = document.getElementById(`${chartId}-twin`);
  if (!bar) {
    bar = document.createElement('div');
    bar.id = `${chartId}-twin`;
    bar.className = 'twin-bar';
    bar.innerHTML =
      '<button type="button" class="twin-button" data-action="table" aria-pressed="false">Table</button>' +
      '<button type="button" class="twin-button" data-action="csv">CSV</button>';
    const container = document.createElement('div');
    container.id = `${chartId}-twin-table`;
    container.className = 'twin-table';
    container.hidden = true;
    chart.insertAdjacentElement('afterend', bar);
    bar.insertAdjacentElement('afterend', container);
    bar.addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.dataset.action === 'csv') {
        downloadTwin(chartId);
        return;
      }
      const open = container.hidden;
      container.hidden = !open;
      button.setAttribute('aria-pressed', String(open));
      if (open) renderTwinTable(chartId);
    });
  }
  bar.hidden = false;
  if (!document.getElementById(`${chartId}-twin-table`).hidden) renderTwinTable(chartId);
}

/** Withdraw a chart's twin when the chart has nothing to show. */
function clearTwin(chartId) {
  twinTables.delete(chartId);
  const bar = document.getElementById(`${chartId}-twin`);
  const container = document.getElementById(`${chartId}-twin-table`);
  if (bar) bar.hidden = true;
  if (container) container.hidden = true;
}

/**
 * Arrange several series, each on its own x values, as one table keyed by x.
 *
 * Series that share the table's x array are read by position; the others — a
 * flow recorded only on steps with trades — are looked up by x value, with a gap
 * where they have no observation.
 */
function tableFromSeries(axisName, xValues, series) {
  const lookups = series.map((entry) => {
    if (entry.x === xValues) return null;
    const lookup = new Map();
    entry.x.forEach((x, index) => lookup.set(x, entry.y[index]));
    return lookup;
  });
  return {
    columns: [axisName, ...series.map((entry) => entry.name)],
    rows: xValues.map((x, index) => [
      x,
      ...series.map((entry, position) => {
        const lookup = lookups[position];
        if (!lookup) return entry.y[index] === undefined ? null : entry.y[index];
        return lookup.has(x) ? lookup.get(x) : null;
      }),
    ]),
  };
}

/* --------------------------------------------------------------- fetching */

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch (error) {
      /* The error body was not JSON; the status message stands. */
    }
    throw new Error(detail);
  }
  return response.json();
}

function showStatus(message, isError) {
  elements.status.textContent = message;
  elements.status.classList.toggle('is-error', Boolean(isError));
  elements.status.hidden = false;
}

function hideStatus() {
  elements.status.hidden = true;
}

/**
 * Show exactly one of the four pages: the placeholder, a run, a cohort, or a
 * calibration study. Four independent hidden flags drifted out of step whenever a
 * new page was added, leaving two pages visible at once.
 */
function showView(name) {
  elements.placeholder.hidden = name !== 'placeholder';
  elements.runView.hidden = name !== 'run';
  elements.cohortView.hidden = name !== 'cohort';
  elements.calibrationView.hidden = name !== 'calibration';
}

/* -------------------------------------------------------------- catalogue */

//: Mirrors MAXIMUM_COHORT_RUNS in web/cohort_view.py. Kept here so the sidebar
//: can disable Compare with a reason rather than sending a request that 422s.
const MAXIMUM_COHORT_RUNS = 64;


/** Build the sidebar label summarising a run's headline settings. */
function runSummaryText(run) {
  const parts = [];
  if (run.time_steps !== null && run.time_steps !== undefined) {
    parts.push(`${Number(run.time_steps).toLocaleString('en-GB')} steps`);
  }
  if (run.seed !== null && run.seed !== undefined) {
    parts.push(`seed ${run.seed}`);
  }
  const switches = [];
  if (run.prospect_theory_enabled) switches.push('CPT');
  if (run.social_enabled) switches.push('social');
  if (run.short_selling_enabled) switches.push('shorts');
  if (switches.length) parts.push(switches.join(' · '));
  return parts.join('  ·  ');
}

function matchesFilter(experiment, run) {
  if (!state.filterText) return true;
  const haystack = `${experiment.name} ${run.run_id}`.toLowerCase();
  return haystack.includes(state.filterText);
}

function renderCatalogue() {
  const catalogue = state.catalogue;
  elements.runList.innerHTML = '';

  if (!catalogue || catalogue.run_count === 0) {
    elements.sidebarCount.textContent = 'No archived runs found';
    return;
  }

  let visibleRuns = 0;
  catalogue.experiments.forEach((experiment) => {
    const runs = experiment.runs.filter((run) => matchesFilter(experiment, run));
    if (!runs.length) return;
    visibleRuns += runs.length;

    const group = document.createElement('div');
    group.className = 'experiment-group';

    const heading = document.createElement('div');
    heading.className = 'experiment-name';
    heading.title = experiment.path;
    const selectAll = document.createElement('label');
    selectAll.className = 'select-all';
    const selectAllBox = document.createElement('input');
    selectAllBox.type = 'checkbox';
    selectAllBox.checked = runs.every((run) => state.selectedPaths.has(run.path));
    const ticks = [];
    selectAllBox.addEventListener('change', () => {
      runs.forEach((run, position) => {
        if (selectAllBox.checked) state.selectedPaths.add(run.path);
        else state.selectedPaths.delete(run.path);
        ticks[position].checked = selectAllBox.checked;
      });
      renderCohortBar();
    });
    selectAll.appendChild(selectAllBox);
    selectAll.append(String(runs.length));

    const name = document.createElement('span');
    name.textContent = experiment.name;
    heading.appendChild(name);
    heading.appendChild(selectAll);
    group.appendChild(heading);

    runs.forEach((run) => {
      const row = document.createElement('div');
      row.className = 'run-row';

      const tick = document.createElement('input');
      tick.type = 'checkbox';
      tick.className = 'run-checkbox';
      tick.checked = state.selectedPaths.has(run.path);
      tick.setAttribute('aria-label', `Select ${run.run_id} for comparison`);
      // Ticking updates the selection in place rather than re-rendering the
      // list. Rebuilding it would destroy the checkbox mid-click and take the
      // keyboard focus with it, which makes ticking several runs in a row
      // impossible without the mouse.
      tick.addEventListener('change', () => {
        if (tick.checked) state.selectedPaths.add(run.path);
        else state.selectedPaths.delete(run.path);
        selectAllBox.checked = runs.every((entry) => state.selectedPaths.has(entry.path));
        renderCohortBar();
      });
      ticks.push(tick);

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'run-button';
      button.dataset.path = run.path;
      button.classList.toggle('is-selected', run.path === state.selectedPath);
      button.innerHTML =
        `<span class="run-button-id">${escapeHtml(run.run_id)}</span>` +
        `<span class="run-button-meta">${escapeHtml(runSummaryText(run))}</span>`;
      button.addEventListener('click', () => selectRun(run.path));

      row.appendChild(tick);
      row.appendChild(button);
      group.appendChild(row);
    });

    elements.runList.appendChild(group);
  });

  const total = catalogue.run_count;
  elements.sidebarCount.textContent = state.filterText
    ? `${visibleRuns} of ${total} runs`
    : `${total} runs in ${catalogue.experiment_count} groups`;
  renderCohortBar();
}

/** Show how many runs are ticked, and whether they can be compared yet. */
function renderCohortBar() {
  const count = state.selectedPaths.size;
  elements.cohortBar.hidden = count === 0;
  if (!count) return;
  const overLimit = count > MAXIMUM_COHORT_RUNS;
  elements.cohortBarCount.textContent = overLimit
    ? `${count} selected — at most ${MAXIMUM_COHORT_RUNS}`
    : `${count} selected`;
  elements.cohortCompare.disabled = count < 2 || overLimit;
}

/* -------------------------------------------------------------- rendering */

function renderProvenance(identity, view) {
  const entries = [
    ['Experiment', identity.experiment_name],
    ['Label', identity.run_label],
    ['Created', identity.created_at],
    ['Status', identity.status],
    ['Model', identity.model_version],
    [
      'Commit',
      identity.git_commit
        ? `${identity.git_commit.slice(0, 10)}${identity.git_dirty ? ' (dirty)' : ''}`
        : null,
    ],
    ['Config hash', identity.config_hash],
    ['Phase', view.phase],
    ['Price column', view.price_column],
    ['Markets', view.assets.count > 1 ? view.assets.names.join(', ') : null],
  ].filter(([, value]) => value !== null && value !== undefined && value !== '');

  elements.runProvenance.innerHTML = entries
    .map(([label, value]) => `<span>${escapeHtml(label)} <strong>${escapeHtml(value)}</strong></span>`)
    .join('');
}

function renderParameters(parameters) {
  elements.runParameters.innerHTML = parameters
    .map((parameter) => {
      const isOn = parameter.kind === 'switch' && parameter.value === true;
      return (
        `<span class="parameter-chip${isOn ? ' is-on' : ''}">` +
        `${escapeHtml(parameter.label)} <b>${escapeHtml(formatParameter(parameter))}</b></span>`
      );
    })
    .join('');
}

/** Show each asset's generating parameters, which differ market by market. */
function renderAssetLegend(assets) {
  if (assets.count < 2 || !assets.configuration.length) {
    elements.assetLegend.innerHTML = '';
    return;
  }
  const order = assets.names;
  elements.assetLegend.innerHTML = assets.configuration
    .map((entry) => {
      const index = Math.max(0, order.indexOf(entry.asset));
      const details = [
        entry.primary ? 'primary' : null,
        entry.enabled ? null : 'disabled',
        entry.process,
        entry.initial_price === null ? null : `start ${formatValue(entry.initial_price, 'price')}`,
        entry.drift_per_step === null ? null : `drift ${formatValue(entry.drift_per_step, 'scientific')}`,
        entry.shock_std_dev === null ? null : `shock ${formatValue(entry.shock_std_dev, 'scientific')}`,
        entry.tick_size === null ? null : `tick ${formatValue(entry.tick_size, 'price')}`,
      ].filter(Boolean);
      return (
        `<span class="parameter-chip asset-chip">${swatch(index)}` +
        `<span class="asset-name">${escapeHtml(entry.asset)}</span>` +
        `<span class="asset-detail">${escapeHtml(details.join(' · '))}</span></span>`
      );
    })
    .join('');
}

function renderStylisedFacts(facts, assets) {
  const showNames = assets.count > 1;
  elements.factGrid.innerHTML = facts
    .map((fact) => {
      const blocks = assets.names
        .map((name, index) => {
          const entry = fact.assets[name] || {};
          const evidence = (entry.evidence || [])
            .map(
              (item) =>
                `<div><span>${escapeHtml(item.label)}</span>` +
                `<b>${escapeHtml(formatValue(item.value, item.format))}</b></div>`
            )
            .join('');
          const heading = showNames
            ? `<span class="fact-asset-name">${swatch(index)}${escapeHtml(name)}</span>`
            : '';
          return (
            `<div class="fact-asset" data-verdict="${escapeHtml(entry.verdict || 'unavailable')}">` +
            heading +
            `<span class="fact-verdict">${escapeHtml(entry.conclusion || 'Not available')}</span>` +
            `<div class="fact-evidence">${evidence}</div></div>`
          );
        })
        .join('');
      return (
        `<div class="fact-card">` +
        `<h3>${escapeHtml(fact.fact)}</h3>` +
        `<p class="fact-expectation">${escapeHtml(fact.expectation)}</p>` +
        blocks +
        `</div>`
      );
    })
    .join('');
}

/** Render each metric group as a table with one column per traded market. */
function renderMetricGroups(groups, assets) {
  const headers = assets.names
    .map((name, index) =>
      assets.count > 1
        ? `<th>${swatch(index)}${escapeHtml(name)}</th>`
        : '<th>Value</th>'
    )
    .join('');

  elements.metricSections.innerHTML = groups
    .map((group) => {
      const rows = group.metrics
        .map((metric) => {
          const source =
            metric.source === 'python diagnostics'
              ? ''
              : `<span class="metric-source">${escapeHtml(metric.source)}</span>`;
          // Iterate the asset order, never the value keys: a "primary" row
          // carries one value and must leave the other columns visibly empty
          // rather than repeating a number under another market's heading.
          const cells = assets.names
            .map((name) => {
              const value = metric.values[name];
              const isMissing = value === null || value === undefined;
              const title =
                isMissing && metric.scope === 'primary'
                  ? ' title="Recorded by the simulator for the primary asset only."'
                  : '';
              return (
                `<td class="metric-number${isMissing ? ' is-missing' : ''}"${title}>` +
                `${escapeHtml(formatValue(value, metric.format))}</td>`
              );
            })
            .join('');
          return (
            `<tr${metric.emphasis ? ' class="is-emphasis"' : ''}>` +
            `<td>${escapeHtml(metric.label)}${source}</td>${cells}</tr>`
          );
        })
        .join('');
      return (
        `<section class="panel">` +
        `<div class="panel-heading"><h2>${escapeHtml(group.title)}</h2></div>` +
        `<div class="table-scroll"><table class="metric-table">` +
        `<thead><tr><th>Metric</th>${headers}</tr></thead>` +
        `<tbody>${rows}</tbody></table></div></section>`
      );
    })
    .join('');
}

function renderTiles(container, metrics) {
  container.innerHTML = metrics
    .map((metric) => {
      const isMissing = metric.value === null || metric.value === undefined;
      return (
        `<div class="metric-tile${metric.emphasis ? ' is-emphasis' : ''}">` +
        `<span class="metric-label">${escapeHtml(metric.label)}</span>` +
        `<span class="metric-value${isMissing ? ' is-missing' : ''}">` +
        `${escapeHtml(formatValue(metric.value, metric.format))}</span></div>`
      );
    })
    .join('');
}

function renderCrossAsset(crossAsset) {
  elements.crossAssetPanel.hidden = !crossAsset.available;
  if (!crossAsset.available) return;
  renderTiles(elements.crossAssetMetrics, crossAsset.metrics);
  drawCrossAssetCharts(crossAsset);
}

function renderAgents(agents, protagonist) {
  renderTiles(elements.agentMetrics, agents.metrics);
  elements.agentMessage.hidden = !agents.message;
  elements.agentMessage.textContent = agents.message || '';

  if (!agents.available || !agents.rows.length) {
    elements.agentTable.innerHTML = '';
    Plotly.purge('chart-agent-wealth');
    document.getElementById('chart-agent-wealth').innerHTML = '';
    renderSocialMap(null, null);
    return;
  }

  // The table lists each recorded rule; the colour dot beside it is the family's,
  // so a row reads against the same key as every chart.
  const familyByLabel = {};
  ((agents.wealth_distribution || {}).strategies || []).forEach((entry) => {
    familyByLabel[entry.strategy] = entry.family;
  });
  const dot = (label) => {
    const token = STRATEGY_COLOUR_TOKENS[familyByLabel[label]];
    return token
      ? `<span class="strategy-swatch" style="background:${cssValue(token)}"></span>`
      : '';
  };

  const headers = agents.columns
    .map((column) => `<th>${escapeHtml(column.label)}</th>`)
    .join('');
  const rows = agents.rows
    .map((row) => {
      const cells = agents.columns
        .map((column) => {
          const value = row[column.key];
          const isMissing = value === null || value === undefined;
          return (
            `<td class="metric-number${isMissing ? ' is-missing' : ''}">` +
            `${escapeHtml(formatValue(value, column.format))}</td>`
          );
        })
        .join('');
      return `<tr><td>${dot(row.strategy)}${escapeHtml(row.strategy)}</td>${cells}</tr>`;
    })
    .join('');

  elements.agentTable.innerHTML =
    `<table class="agent-table"><thead><tr><th>Strategy</th>${headers}</tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
  drawAgentWealthChart(agents, protagonist);
  renderSocialMap(agents.social_map, protagonist);
}

function renderProtagonist(protagonist) {
  elements.protagonistMessage.hidden = !protagonist.message;
  elements.protagonistMessage.textContent = protagonist.message || '';

  if (!protagonist.available) {
    elements.protagonistIdentity.innerHTML = '';
    elements.protagonistMetrics.innerHTML = '';
    Plotly.purge('chart-protagonist-wealth');
    clearTwin('chart-protagonist-wealth');
    document.getElementById('chart-protagonist-wealth').innerHTML = '';
    return;
  }

  renderTiles(elements.protagonistMetrics, protagonist.metrics);
  elements.protagonistIdentity.innerHTML = protagonistChips(protagonist.identity);
  drawProtagonistWealthChart(protagonist.trajectory);
}

/** Describe who the protagonist is, beside the panel heading. */
function protagonistChips(identity) {
  if (!identity) return '';
  const chips = [
    identity.agent_id === null ? null : `agent #${formatValue(identity.agent_id, 'integer')}`,
    identity.strategy ? identity.strategy.replace(/_/g, ' ') : null,
    identity.initial_wealth === null
      ? null
      : `started ${formatValue(identity.initial_wealth, 'amount')}`,
    identity.prospect_theory_enabled
      ? `CPT λ ${formatValue(identity.loss_aversion, 'decimal')}`
      : 'expected utility',
  ].filter(Boolean);
  return chips
    .map((chip) => `<span class="parameter-chip">${escapeHtml(chip)}</span>`)
    .join('');
}

function renderFooter(view) {
  const notes = [];
  const source =
    view.assets.source === 'asset_timeseries'
      ? `asset_timeseries.csv (${view.assets.count} market${view.assets.count > 1 ? 's' : ''})`
      : 'step_timeseries.csv';
  notes.push(
    `Diagnostics recomputed from ${escapeHtml(view.run_id)} at the ` +
      `${escapeHtml(view.phase)} phase, reading ${escapeHtml(source)}; returns ` +
      `${escapeHtml(view.assets.return_source)}; significance level ${view.significance_level}.`
  );
  view.assets.notes.forEach((note) => notes.push(escapeHtml(note)));
  if (view.series.downsampled) {
    notes.push(
      `Charts are thinned to every ${view.series.stride}th observation for rendering; ` +
        `all statistics use the complete series.`
    );
  }
  if (view.diagnostic_message) {
    notes.push(escapeHtml(view.diagnostic_message));
  }
  if (view.agents.message) {
    notes.push(escapeHtml(view.agents.message));
  }
  if (view.protagonist.available && view.protagonist.trajectory.downsampled) {
    notes.push(
      `The protagonist's path is thinned to every ${view.protagonist.trajectory.stride}th ` +
        `step for rendering; his reported rank uses the full agent snapshot.`
    );
  }
  notes.push('Verdicts are screening diagnostics, not causal claims.');
  elements.runFooter.innerHTML = notes.join('<br>');
}

/* ----------------------------------------------------------------- charts */

/* Zoom, pan and reset stay available on hover. The download-as-image button is
 * removed on purpose: the project keeps its results as CSV tables and removed its
 * static image export deliberately; each new chart carries a CSV of its own. */
const PLOT_CONFIG = {
  displayModeBar: 'hover',
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: [
    'toImage',
    'sendDataToCloud',
    'select2d',
    'lasso2d',
    'hoverClosestCartesian',
    'hoverCompareCartesian',
    'toggleSpikelines',
  ],
};

/**
 * Draw a chart, first giving its container the height the layout asks for.
 *
 * Plotly sizes the drawing from ``layout.height`` but leaves the element that
 * holds it alone, so a chart taller than the stylesheet's minimum would spill
 * over whatever follows it and overlap the text beneath. Every chart goes through
 * here so the container always includes the whole figure, axis labels and all.
 */
function drawPlot(target, traces, layout, config) {
  const element = typeof target === 'string' ? document.getElementById(target) : target;
  if (element && layout && layout.height) element.style.height = `${layout.height}px`;
  return Plotly.react(target, traces, layout, config);
}

/** Shared Plotly layout so every chart reads as one figure set. */
function baseLayout(overrides) {
  const gridColour = cssValue('--border');
  const textColour = cssValue('--text-muted');
  return Object.assign(
    {
      margin: { l: 62, r: 18, t: 10, b: 44 },
      height: 330,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: cssValue('--font-sans'), size: 12, color: textColour },
      xaxis: { gridcolor: gridColour, zerolinecolor: gridColour, linecolor: gridColour },
      yaxis: { gridcolor: gridColour, zerolinecolor: gridColour, linecolor: gridColour },
      legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 11 } },
      hovermode: 'x unified',
    },
    overrides || {}
  );
}

/** Build a layout with axis titles, without repeating the base three times. */
function chartLayout(xTitle, yTitle, overrides) {
  const layout = baseLayout(overrides);
  layout.xaxis = Object.assign(baseLayout().xaxis, layout.xaxis || {}, {
    title: { text: xTitle, standoff: 8 },
  });
  layout.yaxis = Object.assign(baseLayout().yaxis, layout.yaxis || {}, {
    title: { text: yTitle, standoff: 8 },
  });
  return layout;
}

/** Scale a track by its own base price so markets at different levels compare. */
function indexTrack(values, basePrice) {
  if (!basePrice) return values;
  return values.map((value) => (value === null ? null : (100 * value) / basePrice));
}

/* ------------------------------------------------------------ market stack */

/*
 * The market story is one figure with a row per measure on a shared time axis,
 * so a crash, the volume that came with it, and the spread that opened beside it
 * can be read at one position with one crosshair. Rows are separate y-axes, never
 * a second scale on one axis: two measures of different units drawn against each
 * other invent a correlation that the data does not contain.
 */

/** Rows top to bottom, each with its share of the height and what it needs. */
const STACK_ROWS = [
  { key: 'price', label: 'Price', height: 220, locked: true },
  { key: 'mispricing', label: 'ln(price / fundamental)', height: 100 },
  { key: 'returns', label: 'Log return', height: 100 },
  { key: 'volatility', label: 'Rolling volatility', height: 100 },
  { key: 'drawdown', label: 'Drawdown from peak', height: 100 },
  { key: 'volume', label: 'Traded volume', height: 100 },
  { key: 'spread', label: 'Bid–ask spread', height: 100 },
  { key: 'flow', label: 'Net order flow by strategy', height: 150 },
  { key: 'risky_weight', label: 'Protagonist · share of wealth in risky assets', height: 100 },
  { key: 'rank', label: 'Protagonist · wealth percentile', height: 100 },
];

//: Space between rows. Each row's caption sits in the gap above it, so the gap
//: must hold a line of text without the caption touching either row's data.
const STACK_ROW_GAP = 28;

//: Opacity of the raw price while a moving average is drawn over it. The raw line
//: has to stay visible, because the average lags it and *when* a crash happened
//: is read from the raw line, but faint enough that the average is the line the
//: eye follows.
const RAW_PRICE_OPACITY_UNDER_AVERAGE = 0.38;

//: The words for each moving average. The keys are the ones the payload uses and
//: the page only supplies names: `label` on the switch, `series` in the legend and
//: the table, `title` as the switch's tooltip. The averages themselves, and the
//: facts the tooltips state, are in `abm_analysis.statistics.smoothing`.
const SMOOTHING_METHOD_TEXT = {
  simple: {
    label: 'Simple',
    series: (length) => `MA ${length}`,
    title:
      'Equal weight on every price in the window, the current one included: the average ' +
      "the model's chartists read. It trails the price.",
  },
  exponential: {
    label: 'Exponential',
    series: (length) => `EMA ${length}`,
    title:
      'Weights fall away with age, so recent prices count most and none drops out ' +
      'abruptly. It trails the price as much as the simple average of the same length.',
  },
  centred: {
    label: 'Centred',
    series: (length) => `centred MA ${length}`,
    title:
      'Equal weight on the prices either side of each step: no lag, but it uses later ' +
      'prices, so it shows the shape of a finished run, not what a trader could have seen.',
  },
};

/** Return the words for one moving average, plain ones for a key the page does not know. */
function smoothingText(method) {
  return (
    SMOOTHING_METHOD_TEXT[method] || {
      label: method,
      series: (length) => `${method} ${length}`,
      title: '',
    }
  );
}

const STRESS_DEFINITION_TEXT = {
  volatility: 'rolling volatility at or above its threshold',
  drawdown: 'drawdown from the running peak at or above its threshold',
  either: 'either trigger',
};

function hasFinite(values) {
  return Array.isArray(values) && values.some((value) => value !== null && value !== undefined);
}

/** Return the market the stack shades and draws flows for. */
function focusedAsset(view) {
  return state.focusAsset && view.assets.names.includes(state.focusAsset)
    ? state.focusAsset
    : view.assets.names[0];
}

/** Return the rows this run has data for, in stack order. */
function availableStackRows(view) {
  const tracks = view.crisis && view.crisis.available ? Object.values(view.crisis.tracks) : [];
  const assetTracks = Object.values(view.series.assets);
  const flow = view.order_flow && view.order_flow.available
    ? view.order_flow.groupings[state.strategyGrouping].assets[focusedAsset(view)]
    : null;
  // The protagonist's own series are keyed to the simulation step; with the
  // row index on the axis they would be drawn at the wrong place.
  const trajectory =
    view.protagonist.available && view.series.step_axis !== 'row_index'
      ? view.protagonist.trajectory
      : null;
  const protagonistSeries = trajectory && trajectory.available ? trajectory.series : {};

  const present = {
    price: true,
    mispricing: tracks.some((track) => hasFinite(track.log_mispricing)),
    returns: assetTracks.some((track) => hasFinite(track.log_return)),
    volatility: tracks.some((track) => hasFinite(track.rolling_volatility)),
    drawdown: tracks.some((track) => hasFinite(track.drawdown)),
    volume: assetTracks.some((track) => hasFinite(track.traded_volume)),
    spread: assetTracks.some((track) => hasFinite(track.bid_ask_spread)),
    flow: Boolean(flow),
    risky_weight: hasFinite(protagonistSeries.risky_weight),
    rank: hasFinite(protagonistSeries.wealth_percentile_rank),
  };
  return STACK_ROWS.filter((row) => present[row.key]);
}

/** Return the rows to draw: every available row the reader has not hidden. */
function visibleStackRows(view) {
  return availableStackRows(view).filter((row) => row.locked || !state.hiddenRows.has(row.key));
}

/**
 * Return a market's moving average of the price for one kind and window, or null.
 *
 * The averages are computed server-side on every step, so a window means steps
 * even when the chart is thinned; this only looks one up. Null means "draw the
 * raw price alone": smoothing is off, or this market has no average to show.
 */
function smoothedPrice(track, method, averagingWindow) {
  if (!averagingWindow || !track.price_moving_average) return null;
  const byWindow = track.price_moving_average[method];
  const values = byWindow ? byWindow[String(averagingWindow)] : null;
  return hasFinite(values) ? values : null;
}

/** Price and fundamental lines for every market, and the moving averages drawn over the price. */
function priceRow(view, ctx) {
  const { series, assets } = view;
  const traces = [];
  const table = [];
  assets.names.forEach((name, index) => {
    const track = series.assets[name];
    if (!track) return;
    const colour = assetColour(index);
    // Both lines are divided by the *market* base price. Indexing the
    // fundamental by its own first value would force the opening mispricing to
    // zero and misdraw the gap the chart exists to show. The average is divided
    // by the same base: it is linear, so averaging the indexed price and indexing
    // the average are the same line.
    const base = ctx.indexed ? track.base_price : null;
    const priceLabel = assets.count > 1 ? `${name} price` : 'Market price';
    const price = ctx.indexed ? indexTrack(track.price, base) : track.price;
    const average = smoothedPrice(track, ctx.smoothingMethod, ctx.smoothing);
    // Under an average the raw price steps back rather than disappearing, and the
    // reader may take it away altogether. With no average to read instead it is
    // always drawn, and the table keeps its column either way.
    if (!average || ctx.showRawPrice) {
      traces.push({
        x: series.step,
        y: price,
        name: priceLabel,
        legendgroup: name,
        type: 'scatter',
        mode: 'lines',
        line: average
          ? { color: withAlpha(colour, RAW_PRICE_OPACITY_UNDER_AVERAGE), width: 1.0 }
          : { color: colour, width: 1.4 },
        yaxis: ctx.yaxis,
      });
    }
    table.push({ name: priceLabel, x: series.step, y: price });
    if (average) {
      const averageLabel = `${priceLabel} · ${smoothingText(ctx.smoothingMethod).series(ctx.smoothing)}`;
      const smoothed = ctx.indexed ? indexTrack(average, base) : average;
      traces.push({
        x: series.step,
        y: smoothed,
        name: averageLabel,
        legendgroup: name,
        type: 'scatter',
        mode: 'lines',
        // Same colour as the market's price, so colour still says which market;
        // weight and the faded raw line say which of the two this is.
        line: { color: colour, width: 2.2 },
        yaxis: ctx.yaxis,
      });
      table.push({ name: averageLabel, x: series.step, y: smoothed });
    }
    if (track.fundamental && track.fundamental.length) {
      const fundamentalLabel = assets.count > 1 ? `${name} fundamental` : 'Fundamental value';
      const fundamental = ctx.indexed ? indexTrack(track.fundamental, base) : track.fundamental;
      traces.push({
        x: series.step,
        y: fundamental,
        name: fundamentalLabel,
        legendgroup: name,
        type: 'scatter',
        mode: 'lines',
        line: {
          // With several markets, colour has to mean "which market" and the
          // dash carries price-versus-fundamental. With one market the colour
          // is free, so the fundamental keeps its own contrasting hue.
          color: assets.count > 1 ? colour : cssValue('--series-fundamental'),
          width: 1.2,
          dash: 'dot',
        },
        yaxis: ctx.yaxis,
      });
      table.push({ name: fundamentalLabel, x: series.step, y: fundamental });
    }
  });
  return { traces, table, shapes: [] };
}

/** One line per market on a single measure shared by every market. */
function perAssetLines(view, ctx, valuesOf, options) {
  const { series, assets } = view;
  const traces = [];
  const table = [];
  assets.names.forEach((name, index) => {
    const values = valuesOf(name);
    if (!hasFinite(values)) return;
    const label = assets.count > 1 ? `${name} ${options.label}` : options.label;
    const colour =
      assets.count > 1 ? assetColour(index) : cssValue(options.singleColour || '--series-returns');
    const plotted = options.transform ? options.transform(values) : values;
    const trace = {
      x: series.step,
      y: plotted,
      name: label,
      legendgroup: name,
      showlegend: false,
      type: 'scatter',
      mode: 'lines',
      line: { color: colour, width: options.width || 1.1, shape: options.shape || 'linear' },
      opacity: assets.count > 1 ? 0.85 : 1,
      yaxis: ctx.yaxis,
    };
    if (options.fill) {
      trace.fill = 'tozeroy';
      trace.fillcolor = withAlpha(colour, assets.count > 1 ? 0.1 : 0.2);
    }
    traces.push(trace);
    table.push({ name: label, x: series.step, y: values });
  });
  return { traces, table };
}

/** Rows read from the crisis payload: mispricing, volatility and drawdown. */
function crisisRow(view, ctx, key, options) {
  const tracks = view.crisis.tracks;
  const { traces, table } = perAssetLines(
    view,
    ctx,
    (name) => (tracks[name] ? tracks[name][key] : []),
    options
  );
  return { traces, table, shapes: options.shapes ? options.shapes(view, ctx) : [] };
}

/** A horizontal reference line across one row, in that row's own units. */
function thresholdLine(ctx, value, colour) {
  return {
    type: 'line',
    xref: 'paper',
    x0: 0,
    x1: 1,
    yref: ctx.yaxis,
    y0: value,
    y1: value,
    line: { color: colour, width: 1, dash: 'dot' },
  };
}

function volatilityShapes(view, ctx) {
  const thresholds = view.crisis.rule.volatility_threshold || {};
  return view.assets.names
    .map((name, index) => {
      const value = thresholds[name];
      if (value === null || value === undefined) return null;
      return thresholdLine(ctx, value, view.assets.count > 1 ? assetColour(index) : cssValue('--text-faint'));
    })
    .filter(Boolean);
}

function drawdownShapes(view, ctx) {
  return [thresholdLine(ctx, -view.crisis.rule.drawdown_threshold, cssValue('--text-faint'))];
}

/** Net order flow by strategy, signed and stacked, for the market in focus. */
function flowRow(view, ctx) {
  const grouping = view.order_flow.groupings[state.strategyGrouping];
  const block = grouping.assets[ctx.focus];
  const styles = strategyStyles(grouping.groups, (group) => grouping.family_of_group[group]);
  const traces = [];
  const table = [];
  grouping.groups.forEach((group) => {
    const values = block.net[group];
    if (!values) return;
    const style = styles[group];
    traces.push({
      x: block.x,
      y: values,
      name: prettyStrategy(group),
      legendgroup: 'flow',
      type: 'bar',
      // The surface-coloured outline is the gap between stacked segments; it
      // separates fills without drawing a border around them.
      marker: {
        color: withAlpha(style.colour, style.opacity),
        line: { color: cssValue('--surface'), width: 2 },
      },
      yaxis: ctx.yaxis,
    });
    table.push({ name: `net flow · ${prettyStrategy(group)}`, x: block.x, y: values });
  });
  return { traces, table, shapes: [] };
}

/** The protagonist's own series, which are keyed to the simulation step. */
function protagonistRow(view, ctx, key, label, colour, width) {
  const trajectory = view.protagonist.trajectory;
  const values = trajectory.series[key];
  return {
    traces: [
      {
        x: trajectory.step,
        y: values,
        name: label,
        showlegend: false,
        type: 'scatter',
        mode: 'lines',
        line: { color: colour, width },
        yaxis: ctx.yaxis,
      },
    ],
    table: [{ name: label, x: trajectory.step, y: values }],
    shapes: [],
  };
}

/** Build one row's traces, table columns and reference shapes. */
function buildStackRow(view, key, ctx) {
  switch (key) {
    case 'price':
      return priceRow(view, ctx);
    case 'mispricing':
      return crisisRow(view, ctx, 'log_mispricing', {
        label: 'ln(P/F)',
        shapes: () => [thresholdLine(ctx, 0, cssValue('--border-strong'))],
      });
    case 'returns': {
      const { traces, table } = perAssetLines(
        view,
        ctx,
        (name) => (view.series.assets[name] || {}).log_return,
        { label: 'log return', width: 0.9 }
      );
      return { traces, table, shapes: [] };
    }
    case 'volatility':
      return crisisRow(view, ctx, 'rolling_volatility', {
        label: 'rolling volatility',
        shapes: volatilityShapes,
      });
    case 'drawdown':
      return crisisRow(view, ctx, 'drawdown', {
        label: 'drawdown',
        // Drawn as the fall below the old high, so it hangs down from zero.
        transform: (values) => values.map((value) => (value === null ? null : -value)),
        fill: true,
        shapes: drawdownShapes,
      });
    case 'volume': {
      const { traces, table } = perAssetLines(
        view,
        ctx,
        (name) => (view.series.assets[name] || {}).traded_volume,
        { label: 'volume', shape: 'hv', fill: true, width: 0.8, singleColour: '--series-returns' }
      );
      return { traces, table, shapes: [] };
    }
    case 'spread': {
      const { traces, table } = perAssetLines(
        view,
        ctx,
        (name) => (view.series.assets[name] || {}).bid_ask_spread,
        { label: 'spread', width: 1.1 }
      );
      return { traces, table, shapes: [] };
    }
    case 'flow':
      return flowRow(view, ctx);
    case 'risky_weight':
      return protagonistRow(view, ctx, 'risky_weight', 'Protagonist risky weight', cssValue('--protagonist'), 1.6);
    case 'rank':
      return protagonistRow(
        view,
        ctx,
        'wealth_percentile_rank',
        'Protagonist wealth percentile',
        cssValue('--protagonist'),
        1.2
      );
    default:
      return { traces: [], table: [], shapes: [] };
  }
}

/** Per-row axis settings: ranges and number formats that suit each measure. */
function stackAxisOptions(key) {
  switch (key) {
    case 'volatility':
    case 'volume':
    case 'spread':
      return { rangemode: 'tozero' };
    case 'drawdown':
      return { tickformat: '.0%' };
    case 'risky_weight':
      return { range: [0, 1], tickformat: '.0%' };
    case 'rank':
      return { range: [0, 1], tickformat: '.0%' };
    default:
      return {};
  }
}

/** Shade the market in focus where it was stressed, and mark the end of warm-up. */
function stressShapes(view) {
  const shapes = [];
  const crisis = view.crisis;
  if (!crisis || !crisis.available) return shapes;
  const asset = crisis.assets[focusedAsset(view)];
  if (asset) {
    const intervals = asset.definitions[state.stressDefinition].intervals;
    const fill = withAlpha(cssValue('--text-faint'), 0.16);
    intervals.forEach(([first, last]) => {
      shapes.push({
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: first - 0.5,
        x1: last + 0.5,
        y0: 0,
        y1: 1,
        fillcolor: fill,
        line: { width: 0 },
        layer: 'below',
      });
    });
  }
  if (crisis.warmup_end !== null && crisis.warmup_end !== undefined) {
    shapes.push({
      type: 'line',
      xref: 'x',
      x0: crisis.warmup_end,
      x1: crisis.warmup_end,
      yref: 'paper',
      y0: 0,
      y1: 1,
      line: { color: cssValue('--text-muted'), width: 1.2 },
    });
  }
  return shapes;
}

function drawMarketStack(view) {
  const indexed = state.priceScale === 'indexed';
  const focus = focusedAsset(view);
  const rows = visibleStackRows(view);

  const gridColour = cssValue('--border');
  const plotHeight =
    rows.reduce((sum, row) => sum + row.height, 0) + STACK_ROW_GAP * (rows.length - 1);
  const margin = { l: 66, r: 18, t: 62, b: 56 };
  let top = 0;

  const axisTitle =
    view.series.step_axis === 'row_index' ? 'Row (warm-up rows carry no simulation step)' : 'Step';
  const traces = [];
  const shapes = stressShapes(view);
  const annotations = [];
  const tables = [];
  const layout = {
    margin,
    height: margin.t + plotHeight + margin.b,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: cssValue('--font-sans'), size: 12, color: cssValue('--text-muted') },
    hovermode: 'x unified',
    barmode: 'relative',
    bargap: 0.1,
    // Above the first row's caption, which takes the first lines of the margin.
    legend: {
      orientation: 'h',
      x: 0,
      y: 1 + 30 / plotHeight,
      yanchor: 'bottom',
      font: { size: 11 },
    },
  };

  rows.forEach((row, position) => {
    const axisNumber = position + 1;
    const yaxis = axisNumber === 1 ? 'y' : `y${axisNumber}`;
    const built = buildStackRow(view, row.key, {
      indexed,
      focus,
      yaxis,
      smoothing: state.priceSmoothing,
      smoothingMethod: state.priceSmoothingMethod,
      showRawPrice: state.showRawPrice,
    });
    traces.push(...built.traces);
    shapes.push(...built.shapes);
    tables.push(...built.table);

    const upper = 1 - top / plotHeight;
    const lower = 1 - (top + row.height) / plotHeight;
    layout[axisNumber === 1 ? 'yaxis' : `yaxis${axisNumber}`] = Object.assign(
      {
        domain: [lower, upper],
        anchor: 'x',
        gridcolor: gridColour,
        zerolinecolor: gridColour,
        linecolor: gridColour,
        tickfont: { size: 10 },
        nticks: row.key === 'price' ? 6 : 4,
        automargin: true,
      },
      stackAxisOptions(row.key)
    );
    const caption =
      row.key === 'flow' && view.assets.count > 1 ? `${row.label} · ${focus}` : row.label;
    annotations.push({
      xref: 'paper',
      yref: 'paper',
      x: 0,
      y: upper,
      xanchor: 'left',
      yanchor: 'bottom',
      yshift: 4,
      text: caption,
      showarrow: false,
      font: { size: 11, color: cssValue('--text-muted') },
    });
    top += row.height + STACK_ROW_GAP;
  });

  // One x-axis for every row, so zooming or panning moves them all together and
  // a position reads the same in each. It is anchored to the bottom row, which
  // is where its labels and title are drawn.
  layout.xaxis = {
    anchor: rows.length === 1 ? 'y' : `y${rows.length}`,
    domain: [0, 1],
    gridcolor: gridColour,
    zerolinecolor: gridColour,
    linecolor: gridColour,
    title: { text: axisTitle, standoff: 8 },
    // One crosshair across every row.
    showspikes: true,
    spikemode: 'across',
    spikesnap: 'cursor',
    spikethickness: 1,
    spikecolor: cssValue('--text-faint'),
    spikedash: 'solid',
  };
  // A unified hover label normally lists only the row under the pointer. 'axis'
  // extends it to every row that shares this x-axis, so one label reads the whole
  // market at that step.
  layout.hoversubplots = 'axis';
  // Series names are long once several markets share one label; the default cuts
  // them at fifteen characters and leaves "alpha fundam…".
  layout.hoverlabel = { namelength: -1 };
  layout.shapes = shapes;
  layout.annotations = annotations;

  drawPlot('chart-stack', traces, layout, PLOT_CONFIG);
  setTwin('chart-stack', `${view.run_id}_market_story`, tableFromSeries(
    view.series.step_axis === 'row_index' ? 'row_index' : 'simulation_step',
    view.series.step,
    tables
  ));
}

/** Build the controls that scope the stack: definition, market, and rows shown. */
function renderStackControls(view) {
  const crisis = view.crisis;
  const hasCrisis = Boolean(crisis && crisis.available);
  elements.stressDefinition.hidden = !hasCrisis;
  if (hasCrisis) {
    if (!crisis.definitions.includes(state.stressDefinition)) {
      state.stressDefinition = crisis.default_definition;
    }
    setSegmented(elements.stressDefinition, state.stressDefinition);
  }

  state.focusAsset = focusedAsset(view);
  fillSegmented(
    elements.focusAsset,
    view.assets.names.map((name) => ({ value: name, label: name })),
    state.focusAsset
  );

  renderSmoothingControl(view);

  const toggles = availableStackRows(view).filter((row) => !row.locked);
  elements.rowToggles.hidden = toggles.length === 0;
  elements.rowToggles.innerHTML = toggles.length
    ? '<span>Rows</span>' +
      toggles
        .map(
          (row) =>
            `<button type="button" class="chip-toggle" data-row="${row.key}" ` +
            `aria-pressed="${state.hiddenRows.has(row.key) ? 'false' : 'true'}">` +
            `${escapeHtml(row.label)}</button>`
        )
        .join('')
    : '';

  elements.stackMessage.hidden = !(crisis && !crisis.available && crisis.message);
  elements.stackMessage.textContent = crisis && crisis.message ? crisis.message : '';
}

/** Name what one observation of the run's x-axis is, for wording about windows. */
function observationUnit(view) {
  return view.series.step_axis === 'row_index' ? 'rows' : 'steps';
}

/** Return the moving-average windows this run offers, shortest first. */
function offeredSmoothingWindows(view) {
  const smoothing = view.series.smoothing;
  return smoothing && Array.isArray(smoothing.windows) ? smoothing.windows : [];
}

/** Return the moving averages this run offers, as the payload lists them. */
function offeredSmoothingMethods(view) {
  const smoothing = view.series.smoothing;
  return smoothing && Array.isArray(smoothing.methods) ? smoothing.methods : [];
}

/**
 * Build the price-smoothing switches from what the payload offers.
 *
 * The windows and the kinds of average both come from the server, which only
 * offers a window the run is long enough for, so the page never holds a list of
 * its own that could disagree with the numbers it was sent. With no window on
 * offer the switches stay hidden. A choice made on an earlier run is kept if this
 * run still offers it and dropped if not.
 */
function renderSmoothingControl(view) {
  const windows = offeredSmoothingWindows(view);
  const methods = offeredSmoothingMethods(view).map((method) => method.key);
  const defaultMethod =
    (view.series.smoothing && view.series.smoothing.default_method) || methods[0] || 'simple';
  if (!windows.includes(state.priceSmoothing)) state.priceSmoothing = 0;
  if (!methods.includes(state.priceSmoothingMethod)) state.priceSmoothingMethod = defaultMethod;
  const unit = observationUnit(view);

  fillSegmented(
    elements.priceSmoothing,
    [
      { value: '0', label: 'Raw' },
      ...windows.map((length) => ({ value: String(length), label: `MA ${length}` })),
    ],
    String(state.priceSmoothing)
  );
  Array.from(elements.priceSmoothing.querySelectorAll('button')).forEach((button) => {
    const length = Number(button.dataset.value);
    button.title = length
      ? `Smooth the price over ${length} ${unit}`
      : 'The price as simulated, without smoothing';
  });

  fillSegmented(
    elements.priceSmoothingMethod,
    methods.map((method) => ({ value: method, label: smoothingText(method).label })),
    state.priceSmoothingMethod
  );
  Array.from(elements.priceSmoothingMethod.querySelectorAll('button')).forEach((button) => {
    button.title = smoothingText(button.dataset.value).title;
  });

  syncSmoothingControls(view);
}

/**
 * Show the kind-of-average switch and the raw-price chip only while an average is
 * drawn: with the raw price alone on screen there is nothing for either to change.
 */
function syncSmoothingControls(view) {
  const smoothed = state.priceSmoothing > 0;
  elements.priceSmoothingMethod.hidden = !smoothed || offeredSmoothingMethods(view).length < 2;
  elements.rawPriceToggle.hidden = !smoothed;
  elements.rawPriceToggle.setAttribute('aria-pressed', String(state.showRawPrice));
}

/**
 * Say what the drawn average is, while one is on screen.
 *
 * Three things are easy to misread and so are stated beside the chart. A trailing
 * average starts late, because no value is drawn until a full window of prices
 * exists, and it lags the price, so a crash reaches it after it reached the price:
 * by (h - 1) / 2 steps for the simple and the exponential average alike. A centred
 * average has no lag, but it uses prices from after each step, so it is not what a
 * trader could have seen, and it is blank at both ends. These are facts about the
 * averages, pinned by tests in `tests/python/test_price_smoothing.py`.
 */
function renderSmoothingNote(view) {
  const length = state.priceSmoothing;
  const shown = length > 0 && offeredSmoothingWindows(view).includes(length);
  elements.smoothingNote.hidden = !shown;
  if (!shown) {
    elements.smoothingNote.innerHTML = '';
    return;
  }
  const unit = observationUnit(view);
  const one = unit.slice(0, -1);
  const method = state.priceSmoothingMethod;
  const bold = view.assets.count > 1 ? 'Each bold line is' : 'The bold line is';
  const ofPrice = view.assets.count > 1 ? "that market's price" : 'the price';
  const ofPrices = view.assets.count > 1 ? "that market's" : 'the';
  const rawHint = state.showRawPrice
    ? 'the faint raw line'
    : 'the raw price (the Raw price chip brings it back)';
  const lag = (length - 1) / 2;
  const lagText = Number.isInteger(lag) ? String(lag) : lag.toFixed(1);
  const trailing =
    `It starts once ${length} prices exist, and it trails the price by about ${lagText} ` +
    `${unit}: read <i>when</i> something happened from ${rawHint}, and use the average to ` +
    `see where the price was heading.`;

  if (method === 'exponential') {
    const decay = Math.round((100 * (length - 1)) / (length + 1));
    elements.smoothingNote.innerHTML =
      `<b>Exponential average.</b> ${bold} the exponentially weighted average of ${ofPrice}, ` +
      `with span ${length}: each ${one} further back counts ${decay}% as much as the one ` +
      `after it, so recent prices count most and none drops out abruptly. ${trailing}`;
  } else if (method === 'centred') {
    const blank = Math.ceil((length - 1) / 2);
    elements.smoothingNote.innerHTML =
      `<b>Centred average.</b> ${bold}, at every ${one}, the simple average of ${ofPrices} ` +
      `${length} prices centred on it, so it does not trail the price. It uses prices from ` +
      `<i>after</i> each ${one}, though: it shows the shape of a finished run, not what a ` +
      `trader could have seen at the time, and it is blank for roughly the first and last ` +
      `${blank} ${unit}, where a full window does not fit.`;
  } else {
    elements.smoothingNote.innerHTML =
      `<b>Moving average.</b> ${bold} the simple average of ${ofPrice} over the last ` +
      `${length} ${unit}, the current one included — the kind of average the model's ` +
      `chartists read. ${trailing}`;
  }
}

/** Print the stress rule beside the shading, with what the shaded share means. */
function renderStressRule(view) {
  const crisis = view.crisis;
  if (!crisis || !crisis.available) {
    elements.stackRule.innerHTML = '';
    return;
  }
  const focus = focusedAsset(view);
  const asset = crisis.assets[focus];
  if (!asset) {
    elements.stackRule.innerHTML = '';
    return;
  }
  const definition = asset.definitions[state.stressDefinition];
  const rule = crisis.rule;
  const threshold = rule.volatility_threshold[focus];
  const share = definition.share === null ? '—' : `${(definition.share * 100).toFixed(0)}%`;
  const market = view.assets.count > 1 ? ` of ${escapeHtml(focus)}` : '';

  elements.stackRule.innerHTML =
    `<b>Stress rule.</b> Volatility is the standard deviation of log returns over the last ` +
    `${rule.rolling_window} steps, and counts as high at or above its ` +
    `${Math.round(rule.volatility_quantile * 100)}th percentile within this window` +
    (threshold === null || threshold === undefined
      ? ''
      : ` (${escapeHtml(formatValue(threshold, 'scientific'))})`) +
    `; drawdown is the fall from the running peak, and counts as deep at ` +
    `${Math.round(rule.drawdown_threshold * 100)}% or more. ` +
    `Shaded: <b>${escapeHtml(STRESS_DEFINITION_TEXT[state.stressDefinition])}</b> — ` +
    `${share} of steps${market}.` +
    `<br>Volatility is an <i>event</i> and drawdown a <i>state</i>: a market that falls and does ` +
    `not recover stays in drawdown for the rest of the run. The volatility trigger flags about a ` +
    `fifth of any series by construction, so its shaded share does not say how turbulent a run ` +
    `was; read the volatility row against its dotted threshold.`;
}

/** Compare normal and stress rows on the market in focus, under the chosen definition. */
function renderStressTable(view) {
  const crisis = view.crisis;
  if (!crisis || !crisis.available) {
    elements.stressTable.innerHTML = '';
    return;
  }
  const focus = focusedAsset(view);
  if (!crisis.assets[focus]) {
    elements.stressTable.innerHTML = '';
    return;
  }
  const definition = crisis.assets[focus].definitions[state.stressDefinition];
  const minimum = crisis.minimum_regime_observations;
  const regimes = ['all', 'normal', 'stress'];
  const labels = { all: 'All rows', normal: 'Normal', stress: 'Stress' };

  const headers = regimes
    .map((regime) => {
      const count = definition.regimes[regime].observation_count;
      const thin = count !== null && count < minimum;
      return (
        `<th${thin ? ' class="is-thin"' : ''}` +
        (thin ? ` title="Fewer than ${minimum} observations: read these values with caution."` : '') +
        `>${labels[regime]}</th>`
      );
    })
    .join('');
  const rows = crisis.metrics
    .map((metric) => {
      const cells = regimes
        .map((regime) => {
          const entry = definition.regimes[regime];
          const thin = entry.observation_count !== null && entry.observation_count < minimum;
          const value = entry[metric.key];
          const missing = value === null || value === undefined;
          return (
            `<td class="metric-number${missing ? ' is-missing' : ''}${thin && metric.key !== 'observation_count' ? ' is-thin' : ''}">` +
            `${escapeHtml(formatValue(value, metric.format))}</td>`
          );
        })
        .join('');
      return `<tr><td>${escapeHtml(metric.label)}</td>${cells}</tr>`;
    })
    .join('');
  const market = view.assets.count > 1 ? ` · ${escapeHtml(focus)}` : '';
  elements.stressTable.innerHTML =
    `<table class="metric-table regime-table"><caption>Normal versus stress${market} — ` +
    `stress defined by ${escapeHtml(STRESS_DEFINITION_TEXT[state.stressDefinition])}</caption>` +
    `<thead><tr><th>Metric</th>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
}

/** Redraw everything the stress definition or the market in focus changes. */
function redrawStackScope(view) {
  renderStackControls(view);
  drawMarketStack(view);
  renderSmoothingNote(view);
  renderStressRule(view);
  renderStressTable(view);
}

function drawDistributionChart(distribution, assets) {
  const target = document.getElementById('chart-distribution');
  if (!distribution.available) {
    Plotly.purge('chart-distribution');
    target.textContent = 'Too few returns to estimate a distribution.';
    return;
  }

  const traces = [];
  assets.names.forEach((name, index) => {
    const entry = distribution.assets[name];
    if (!entry || !entry.available) return;
    const colour = assetColour(index);
    if (assets.count === 1) {
      traces.push({
        x: entry.bin_centre,
        y: entry.density,
        name: 'Simulated returns',
        type: 'bar',
        marker: { color: colour, opacity: 0.55 },
        width: entry.bin_width,
      });
    } else {
      traces.push({
        x: entry.bin_centre,
        y: entry.density,
        name,
        type: 'scatter',
        mode: 'lines',
        line: { color: colour, width: 1.6, shape: 'spline' },
      });
    }
    if (entry.normal_grid && entry.normal_grid.length) {
      traces.push({
        x: entry.normal_grid,
        y: entry.normal_density,
        name: assets.count > 1 ? `${name} normal` : 'Normal reference',
        type: 'scatter',
        mode: 'lines',
        line: {
          color: assets.count > 1 ? colour : cssValue('--series-absolute'),
          width: assets.count > 1 ? 1.2 : 1.8,
          dash: assets.count > 1 ? 'dot' : 'solid',
        },
        opacity: assets.count > 1 ? 0.55 : 1,
      });
    }
  });

  drawPlot(
    'chart-distribution',
    traces,
    chartLayout('Log return', 'Density', { bargap: 0.02, hovermode: 'closest' }),
    PLOT_CONFIG
  );
}

const ACF_SERIES = [
  { key: 'raw', label: 'Raw returns', colour: '--series-raw', dash: 'solid' },
  { key: 'absolute', label: 'Absolute returns', colour: '--series-absolute', dash: 'dot' },
  { key: 'squared', label: 'Squared returns', colour: '--series-squared', dash: 'dash' },
];

function drawAutocorrelationChart(autocorrelation, assets, selection) {
  const target = document.getElementById('chart-autocorrelation');
  if (!autocorrelation.available) {
    Plotly.purge('chart-autocorrelation');
    target.textContent = 'Too few returns to estimate an autocorrelation function.';
    return;
  }

  const chosen = selection === 'all' ? ACF_SERIES : ACF_SERIES.filter((s) => s.key === selection);
  const multi = assets.count > 1;
  const traces = [];
  chosen.forEach((series) => {
    assets.names.forEach((name, index) => {
      const entry = autocorrelation.assets[name];
      if (!entry || !entry.available) return;
      traces.push({
        x: entry.lag,
        y: entry[series.key],
        name: multi ? `${name} ${series.label.toLowerCase()}` : series.label,
        type: 'scatter',
        mode: 'lines+markers',
        marker: { size: 4 },
        line: {
          // Colour identifies the market when there is more than one, and the
          // series otherwise; the dash always identifies the series.
          color: multi ? assetColour(index) : cssValue(series.colour),
          width: 1.4,
          dash: chosen.length > 1 ? series.dash : 'solid',
        },
      });
    });
  });

  const band = autocorrelation.confidence_band;
  const layout = chartLayout('Lag', 'Autocorrelation', {
    shapes: band
      ? [
          {
            type: 'rect',
            xref: 'paper',
            x0: 0,
            x1: 1,
            yref: 'y',
            y0: -band,
            y1: band,
            fillcolor: cssValue('--text-faint'),
            opacity: 0.12,
            line: { width: 0 },
            layer: 'below',
          },
        ]
      : [],
  });
  drawPlot('chart-autocorrelation', traces, layout, PLOT_CONFIG);
}

function drawCrossAssetCharts(crossAsset) {
  // Both series here are properties of the *pair*, not of either market, so
  // neither may wear a market's identity colour: the stylesheet's rule is that
  // an asset colour answers "which asset is this", and a correlation between
  // alpha and beta drawn in alpha's blue answers it wrongly. They take the
  // neutral series tone instead, and the axis titles name the pair.
  const pairColour = cssValue('--series-returns');
  const shapes = [];
  if (crossAsset.configured_correlation !== null && crossAsset.configured_correlation !== undefined) {
    shapes.push({
      type: 'line',
      xref: 'paper',
      x0: 0,
      x1: 1,
      yref: 'y',
      y0: crossAsset.configured_correlation,
      y1: crossAsset.configured_correlation,
      line: { color: cssValue('--series-fundamental'), width: 1.4, dash: 'dash' },
      layer: 'below',
    });
  }

  drawPlot(
    'chart-correlation',
    [
      {
        x: crossAsset.step,
        y: crossAsset.rolling_correlation,
        name: `Realised corr(${crossAsset.asset_a}, ${crossAsset.asset_b})`,
        type: 'scatter',
        mode: 'lines',
        line: { color: pairColour, width: 1.3 },
      },
    ],
    chartLayout('Step', `Rolling correlation (${crossAsset.window} steps)`, {
      height: 300,
      yaxis: { range: [-1, 1] },
      shapes,
      showlegend: false,
    }),
    PLOT_CONFIG
  );

  drawPlot(
    'chart-price-ratio',
    [
      {
        x: crossAsset.step,
        y: crossAsset.price_ratio,
        name: `${crossAsset.asset_a} / ${crossAsset.asset_b}`,
        type: 'scatter',
        mode: 'lines',
        line: { color: pairColour, width: 1.3 },
      },
    ],
    chartLayout('Step', `Price ratio ${crossAsset.asset_a} / ${crossAsset.asset_b}`, {
      height: 300,
      showlegend: false,
    }),
    PLOT_CONFIG
  );
}

function drawAgentWealthChart(agents, protagonist) {
  const distribution = agents.wealth_distribution;
  const target = document.getElementById('chart-agent-wealth');
  if (!distribution.available) {
    Plotly.purge('chart-agent-wealth');
    target.textContent = '';
    return;
  }

  // Families by default: six overlaid curves cannot be told apart, three can. The
  // split view keeps each recorded rule, drawn in its family's hue.
  const entries =
    state.strategyGrouping === 'family' && distribution.families
      ? distribution.families
      : distribution.strategies;
  const familyOfEntry = new Map(entries.map((entry) => [entry.strategy, entry.family]));
  const styles = strategyStyles(
    entries.map((entry) => entry.strategy),
    (group) => familyOfEntry.get(group)
  );
  const single = entries.length === 1;
  const traces = entries.map((entry) => {
    const style = styles[entry.strategy];
    return {
      x: distribution.bin_centre,
      y: entry.density,
      name: `${prettyStrategy(entry.strategy)} (${entry.count})`,
      type: 'scatter',
      mode: 'lines',
      fill: single ? 'tozeroy' : 'none',
      fillcolor: single ? withAlpha(style.colour, 0.18) : undefined,
      line: { color: style.colour, width: 1.6, dash: style.dash },
      opacity: style.opacity,
    };
  });

  const layout = chartLayout('Final wealth', 'Density', {
    height: 300,
    hovermode: 'closest',
    legend: { orientation: 'h', y: 1.22, x: 0, font: { size: 11 } },
  });

  /*
   * The protagonist's marker is drawn on this chart rather than on one of his
   * own: his wealth only means something against the distribution it sits in,
   * and a second axis would invite the reader to compare two different scales.
   */
  const marker = protagonist && protagonist.available ? protagonist.wealth_marker : null;
  if (marker !== null && marker !== undefined) {
    const percentile = protagonist.standing ? protagonist.standing.percentile : null;
    layout.shapes = [
      {
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: marker,
        x1: marker,
        y0: 0,
        y1: 1,
        line: { color: cssValue('--protagonist'), width: 2, dash: 'dash' },
      },
    ];
    layout.annotations = [
      {
        x: marker,
        xref: 'x',
        y: 1,
        yref: 'paper',
        yanchor: 'bottom',
        showarrow: false,
        font: { size: 11, color: cssValue('--protagonist') },
        text:
          percentile === null || percentile === undefined
            ? 'protagonist'
            : `protagonist · ${formatValue(percentile, 'percent_fraction')}`,
      },
    ];
  }

  drawPlot('chart-agent-wealth', traces, layout, PLOT_CONFIG);
  setTwin(
    'chart-agent-wealth',
    `${state.view ? state.view.run_id : 'run'}_wealth_density`,
    tableFromSeries(
      'final_wealth',
      distribution.bin_centre,
      entries.map((entry) => ({
        name: `density · ${prettyStrategy(entry.strategy)}`,
        x: distribution.bin_centre,
        y: entry.density,
      }))
    )
  );
}

/* ------------------------------------------------------------- social map */

/** What each colouring of the social-space map measures, and how it is scaled. */
const MAP_COLOURINGS = {
  opinion: { key: 'opinion', label: 'Final opinion', signed: true },
  wealth_change: { key: 'wealth_change', label: 'Wealth change', signed: true },
  loss_aversion: { key: 'loss_aversion', label: 'Loss aversion λ', signed: false },
};

/**
 * Draw every agent at its place in the model's social space.
 *
 * The social channel moves an agent's opinion towards its neighbours', so whether
 * it does anything shows up as structure here: opinions that cluster mean the
 * neighbourhood is shaping them, and opinions scattered at random mean it is not.
 * Hue is spent on the quantity mapped, so the strategy family is carried by
 * marker shape — four hues cannot stay apart in a scatter — and the protagonist
 * is a ring around his marker.
 */
function renderSocialMap(map, protagonist) {
  if (!map || !map.available) {
    elements.agentMap.hidden = true;
    Plotly.purge('chart-social-map');
    clearTwin('chart-social-map');
    return;
  }
  elements.agentMap.hidden = false;
  setSegmented(elements.mapColour, state.mapColour);

  const colouring = MAP_COLOURINGS[state.mapColour] || MAP_COLOURINGS.opinion;
  const values = map[colouring.key];
  const finite = values.filter((value) => value !== null && value !== undefined);
  if (!finite.length) {
    Plotly.purge('chart-social-map');
    clearTwin('chart-social-map');
    elements.socialMapMessage.hidden = false;
    elements.socialMapMessage.textContent =
      `This run records no ${colouring.label.toLowerCase()} for its agents.`;
    return;
  }
  const smallest = Math.min(...finite);
  const largest = Math.max(...finite);
  if (smallest === largest) {
    Plotly.purge('chart-social-map');
    clearTwin('chart-social-map');
    elements.socialMapMessage.hidden = false;
    elements.socialMapMessage.textContent =
      `${colouring.label} is the same for every agent in this run (${formatValue(smallest, 'decimal')}), ` +
      'so there is nothing to map.';
    return;
  }
  elements.socialMapMessage.hidden = true;

  // A signed quantity is centred on zero with equal reach either side, so the
  // neutral midpoint means "none" and the two poles are comparable.
  const reach = Math.max(Math.abs(smallest), Math.abs(largest));
  const scale = colouring.signed
    ? { colorscale: divergingScale(), cmin: -reach, cmax: reach, cmid: 0 }
    : { colorscale: sequentialScale(), cmin: smallest, cmax: largest };

  const families = [...new Set(map.family)];
  const outline = { color: cssValue('--border-strong'), width: 0.6 };
  const traces = [];
  families.forEach((family, order) => {
    const members = map.family.map((value, index) => (value === family ? index : -1)).filter((i) => i >= 0);
    traces.push({
      x: members.map((i) => map.x[i]),
      y: members.map((i) => map.y[i]),
      type: 'scatter',
      mode: 'markers',
      showlegend: false,
      text: members.map(
        (i) =>
          `agent ${map.agent_id[i]} · ${prettyStrategy(map.strategy[i])} · ` +
          `${colouring.label.toLowerCase()} ${formatValue(values[i], 'decimal')}`
      ),
      hovertemplate: '%{text}<extra></extra>',
      marker: Object.assign(
        {
          symbol: FAMILY_SYMBOLS[family] || 'circle',
          size: 9,
          color: members.map((i) => (values[i] === null ? smallest : values[i])),
          line: outline,
          colorbar:
            order === 0
              ? { thickness: 12, title: { text: colouring.label, side: 'right' }, len: 0.8 }
              : undefined,
          showscale: order === 0,
        },
        scale
      ),
    });
  });
  // The legend is a separate set of neutral markers: a data trace's legend entry
  // would take its colour from whichever agent happened to come first.
  families.forEach((family) => {
    traces.push({
      x: [null],
      y: [null],
      type: 'scatter',
      mode: 'markers',
      name: prettyStrategy(family),
      marker: {
        symbol: FAMILY_SYMBOLS[family] || 'circle',
        size: 9,
        color: cssValue('--text-muted'),
        line: outline,
      },
    });
  });

  const flagged = map.is_protagonist.map((value, index) => (value ? index : -1)).filter((i) => i >= 0);
  if (flagged.length) {
    traces.push({
      x: flagged.map((i) => map.x[i]),
      y: flagged.map((i) => map.y[i]),
      type: 'scatter',
      mode: 'markers',
      name: 'Protagonist',
      hoverinfo: 'skip',
      marker: {
        symbol: 'circle-open',
        size: 20,
        color: cssValue('--protagonist'),
        line: { color: cssValue('--protagonist'), width: 2.5 },
      },
    });
  }

  drawPlot(
    'chart-social-map',
    traces,
    chartLayout('Social space · x', 'Social space · y', {
      height: 440,
      hovermode: 'closest',
      xaxis: { constrain: 'domain' },
      yaxis: { scaleanchor: 'x', scaleratio: 1, constrain: 'domain' },
      legend: { orientation: 'h', y: 1.1, x: 0, font: { size: 11 } },
    }),
    PLOT_CONFIG
  );

  setTwin('chart-social-map', `${state.view ? state.view.run_id : 'run'}_social_space`, {
    columns: ['agent_id', 'strategy', 'family', 'x', 'y', 'final_opinion', 'wealth_change', 'loss_aversion'],
    rows: map.agent_id.map((id, index) => [
      id,
      map.strategy[index],
      map.family[index],
      map.x[index],
      map.y[index],
      map.opinion[index],
      map.wealth_change[index],
      map.loss_aversion[index],
    ]),
  });
}

/* --------------------------------------------------------------- order flow */

/** Draw who bought from whom, as a matrix of buyer by seller. */
function drawCounterpartyChart(view) {
  const flow = view.order_flow;
  elements.flowPanel.hidden = !flow;
  if (!flow || !flow.available) {
    Plotly.purge('chart-counterparty');
    clearTwin('chart-counterparty');
    elements.flowMessage.hidden = !(flow && flow.message);
    elements.flowMessage.textContent = flow && flow.message ? flow.message : '';
    return;
  }

  const grouping = flow.groupings[state.strategyGrouping];
  const asset = focusedAsset(view);
  const entry = grouping.assets[asset];
  if (!entry) {
    Plotly.purge('chart-counterparty');
    clearTwin('chart-counterparty');
    elements.flowMessage.hidden = false;
    elements.flowMessage.textContent = `No trades were recorded for ${asset}.`;
    return;
  }

  const warning = flow.checks && flow.checks.balanced === false
    ? `This ledger does not balance (largest net-flow residual ` +
      `${formatValue(flow.checks.net_flow_residual, 'decimal')}): some trades are recorded from one ` +
      `side only, so flows by strategy are incomplete.`
    : '';
  elements.flowMessage.hidden = !warning;
  elements.flowMessage.textContent = warning;

  const share = state.flowMatrixMode === 'share';
  const matrix = share ? entry.counterparty.share : entry.counterparty.volume;
  const labels = grouping.groups.map(prettyStrategy);
  drawPlot(
    'chart-counterparty',
    [
      {
        type: 'heatmap',
        x: labels,
        y: labels,
        z: matrix,
        zmin: 0,
        colorscale: sequentialScale(),
        xgap: 2,
        ygap: 2,
        texttemplate: share ? '%{z:.0%}' : '%{z:,.0f}',
        hovertemplate: share
          ? 'Buyer %{y} bought %{z:.1%} of its purchases from %{x}<extra></extra>'
          : 'Buyer %{y} bought %{z:,.0f} from %{x}<extra></extra>',
        colorbar: {
          thickness: 12,
          tickformat: share ? '.0%' : ',.0f',
          title: { text: share ? "Share of buyer's purchases" : 'Volume bought', side: 'right' },
        },
      },
    ],
    chartLayout('Seller (counterparty)', 'Buyer', {
      height: Math.max(260, 110 + labels.length * 54),
      hovermode: 'closest',
      xaxis: { automargin: true },
      yaxis: { autorange: 'reversed', automargin: true },
    }),
    PLOT_CONFIG
  );

  setTwin('chart-counterparty', `${view.run_id}_counterparty_${state.flowMatrixMode}`, {
    columns: ['buyer \\ seller', ...labels],
    rows: labels.map((label, row) => [label, ...matrix[row]]),
  });
}

/**
 * Draw the protagonist's wealth path against the population he traded in.
 *
 * His wealth alone cannot separate an investor who traded well from one who
 * held a rising asset, so the median and mean are drawn beside it. His percentile
 * rank is the measure that does separate them — a flat rank under a rising wealth
 * line means the whole market rose, and a rising rank means he gained on it — and
 * it sits in its own row on the same time axis rather than on a second y-axis.
 * Two scales on one plot make the alignment of their zero lines arbitrary, and
 * the chart would then suggest a relationship the data does not hold.
 */
function drawProtagonistWealthChart(trajectory) {
  const target = document.getElementById('chart-protagonist-wealth');
  if (!trajectory || !trajectory.available) {
    Plotly.purge('chart-protagonist-wealth');
    clearTwin('chart-protagonist-wealth');
    target.textContent = '';
    return;
  }

  const series = trajectory.series || {};
  const traces = [];
  const columns = [];
  const add = (key, name, line, extra) => {
    if (!series[key]) return;
    traces.push(
      Object.assign(
        { x: trajectory.step, y: series[key], name, type: 'scatter', mode: 'lines', line },
        extra || {}
      )
    );
    columns.push({ name, x: trajectory.step, y: series[key] });
  };
  add('wealth', 'Protagonist wealth', { color: cssValue('--protagonist'), width: 2 });
  add('population_median_wealth', 'Population median', { color: assetColour(0), width: 1.6 });
  add('population_mean_wealth', 'Population mean', { color: assetColour(1), width: 1.2, dash: 'dot' });
  const hasRank = Boolean(series.wealth_percentile_rank);
  add(
    'wealth_percentile_rank',
    'Percentile rank',
    { color: cssValue('--protagonist'), width: 1.2 },
    { yaxis: 'y2', showlegend: false }
  );

  if (!traces.length) {
    Plotly.purge('chart-protagonist-wealth');
    clearTwin('chart-protagonist-wealth');
    target.textContent = '';
    return;
  }

  const grid = cssValue('--border');
  const axis = { gridcolor: grid, zerolinecolor: grid, linecolor: grid, automargin: true };
  const margin = { l: 66, r: 18, t: 44, b: 52 };
  const layout = baseLayout({
    height: hasRank ? 400 : 300,
    margin,
    legend: { orientation: 'h', x: 0, y: 1, yanchor: 'bottom', font: { size: 11 } },
    barmode: 'relative',
  });
  layout.xaxis = Object.assign({}, axis, {
    anchor: hasRank ? 'y2' : 'y',
    title: { text: 'Step', standoff: 8 },
    showspikes: true,
    spikemode: 'across',
    spikethickness: 1,
    spikecolor: cssValue('--text-faint'),
    spikedash: 'solid',
  });
  layout.yaxis = Object.assign({}, axis, {
    domain: hasRank ? [0.34, 1] : [0, 1],
    anchor: 'x',
    title: { text: 'Wealth', standoff: 8 },
  });
  if (hasRank) {
    layout.yaxis2 = Object.assign({}, axis, {
      domain: [0, 0.24],
      anchor: 'x',
      range: [0, 1],
      tickformat: '.0%',
      title: { text: 'Percentile', standoff: 8 },
      nticks: 3,
    });
  }

  drawPlot('chart-protagonist-wealth', traces, layout, PLOT_CONFIG);
  setTwin(
    'chart-protagonist-wealth',
    `${state.view ? state.view.run_id : 'run'}_protagonist_wealth`,
    tableFromSeries('simulation_step', trajectory.step, columns)
  );
}

/* ---------------------------------------------------------- cohort view */

/** Look up a condition's position, which fixes its colour across the page. */
function conditionIndex(cohort, conditionId) {
  return cohort.conditions.findIndex((entry) => entry.condition_id === conditionId);
}

/** Return the market currently in focus, or the only one there is. */
function activeAsset(cohort) {
  if (state.cohortAsset && cohort.assets.names.includes(state.cohortAsset)) {
    return state.cohortAsset;
  }
  return cohort.assets.names[0];
}

/** Rebuild a segmented control's buttons from a list of {value,label}. */
function fillSegmented(container, options, selected) {
  container.innerHTML = options
    .map(
      (option) =>
        `<button type="button" data-value="${escapeHtml(option.value)}">` +
        `${escapeHtml(option.label)}</button>`
    )
    .join('');
  container.hidden = options.length < 2;
  setSegmented(container, selected);
}

function renderConditionLegend(cohort) {
  elements.conditionLegend.innerHTML = cohort.conditions
    .map((condition, index) => {
      const seeds = condition.seed_count === 1 ? '1 seed' : `${condition.seed_count} seeds`;
      return (
        `<span class="condition-chip">${conditionSwatch(index)}` +
        `<span>${escapeHtml(condition.label)}</span>` +
        `<span class="condition-meta">${escapeHtml(seeds)}</span></span>`
      );
    })
    .join('');
}

function renderCohortAssetLegend(cohort) {
  if (cohort.assets.count < 2) {
    elements.cohortAssetLegend.innerHTML = '';
    return;
  }
  elements.cohortAssetLegend.innerHTML = cohort.assets.names
    .map(
      (name, index) =>
        `<span class="parameter-chip asset-chip">${swatch(index)}` +
        `<span class="asset-name">${escapeHtml(name)}</span></span>`
    )
    .join('');
}

/** Verdict tokens in the order the summary strip counts them. */
const VERDICT_ORDER = [
  { token: 'supported', label: 'pass' },
  { token: 'partial', label: 'borderline' },
  { token: 'not-supported', label: 'fail' },
  { token: 'unavailable', label: 'n/a' },
];

const VERDICT_PILL_LABELS = {
  supported: 'Pass',
  partial: 'Borderline',
  'not-supported': 'Fail',
  unavailable: 'N/A',
};

/** Format a verdict statistic or cut-off in the units the rule is stated in. */
function formatVerdictNumber(value, format) {
  if (value === null || value === undefined) {
    return '—';
  }
  switch (format) {
    case 'share':
      return `${(value * 100).toFixed(0)}%`;
    case 'p_value':
      return formatValue(value, 'p_value');
    case 'ratio':
    default:
      return value.toFixed(3);
  }
}

/** Render one cut-off as the inequality the rule actually tests. */
function verdictRule(card, threshold) {
  if (threshold === null || threshold === undefined) {
    return '<td class="metric-number verdict-rule is-missing">—</td>';
  }
  const symbol = card.comparison === '>=' ? '≥' : '≤';
  return (
    `<td class="metric-number verdict-rule">${symbol} ` +
    `${escapeHtml(formatVerdictNumber(threshold, card.value_format))}</td>`
  );
}

function renderVerdicts(cohort) {
  const asset = activeAsset(cohort);
  // A verdict scoped to one market is only shown while that market is in
  // focus; cohort-wide criteria (the distribution tests) carry no asset and
  // are always shown, since they describe the selection as a whole.
  const cards = cohort.verdicts.filter(
    (card) => card.asset === null || card.asset === undefined || card.asset === asset
  );
  elements.verdictMessage.hidden = cards.length > 0;
  if (!cards.length) {
    elements.verdictMessage.textContent =
      'No robustness criteria could be evaluated for this selection.';
    elements.verdictSummary.innerHTML = '';
    elements.verdictTable.innerHTML = '';
    return;
  }

  // The strip counts what is on screen, so it follows the market in focus.
  const seeds = cohort.seed_count === 1 ? '1 seed' : `${cohort.seed_count} seeds`;
  const minimum = cohort.verdict_minimum_seeds;
  const shortfall = minimum && cohort.seed_count < minimum ? minimum - cohort.seed_count : 0;
  const sample =
    `<span class="verdict-n">n = ${escapeHtml(seeds)}` +
    (minimum ? ` · min ${minimum}` : '') +
    (shortfall ? ` · ${shortfall} more needed` : '') +
    '</span>';
  const counts = VERDICT_ORDER.map((entry) => {
    const count = cards.filter((card) => card.token === entry.token).length;
    return (
      `<span class="verdict-count" data-verdict="${entry.token}">` +
      `<b>${count}</b> ${entry.label}</span>`
    );
  }).join('');
  elements.verdictSummary.innerHTML = sample + counts;

  const showScope = cards.some((card) => card.scope);
  const columns = showScope ? 7 : 6;
  const headers =
    '<th>Criterion</th>' +
    (showScope ? '<th>Condition</th>' : '') +
    '<th>Statistic</th><th>Value</th><th>Pass</th><th>Borderline</th><th>Verdict</th>';

  // Rows are grouped by category in the order the server listed them.
  const groups = [];
  cards.forEach((card) => {
    let group = groups.find((entry) => entry.category === card.category);
    if (!group) {
      group = { category: card.category, label: card.category_label, cards: [] };
      groups.push(group);
    }
    group.cards.push(card);
  });

  const body = groups
    .map((group) => {
      const heading =
        `<tr class="verdict-group"><th colspan="${columns}">` +
        `${escapeHtml(group.label || group.category || 'Criteria')}</th></tr>`;
      const rows = group.cards
        .map((card) => {
          const missing = card.value === null || card.value === undefined;
          const sampleSize =
            card.sample_size === null || card.sample_size === undefined
              ? ''
              : `<span class="cell-dispersion">n = ${card.sample_size} ` +
                `${escapeHtml(card.sample_unit || '')}</span>`;
          const value =
            `<td class="metric-number${missing ? ' is-missing' : ''}">` +
            `<span class="cell-mean">` +
            `${escapeHtml(formatVerdictNumber(card.value, card.value_format))}</span>` +
            `${sampleSize}</td>`;
          const pill =
            `<span class="verdict-pill" data-verdict="${escapeHtml(card.token)}" ` +
            `title="${escapeHtml(card.interpretation)}">` +
            `${escapeHtml(VERDICT_PILL_LABELS[card.token] || card.verdict)}</span>`;
          return (
            `<tr><td title="${escapeHtml(card.hypothesis)}">${escapeHtml(card.criterion)}</td>` +
            (showScope ? `<td class="verdict-scope">${escapeHtml(card.scope || '—')}</td>` : '') +
            `<td class="verdict-statistic">${escapeHtml(card.statistic || '')}</td>` +
            value +
            verdictRule(card, card.pass_threshold) +
            verdictRule(card, card.borderline_threshold) +
            `<td class="verdict-cell">${pill}</td></tr>`
          );
        })
        .join('');
      return heading + rows;
    })
    .join('');

  elements.verdictTable.innerHTML =
    `<table class="metric-table verdict-table"><thead><tr>${headers}</tr></thead>` +
    `<tbody>${body}</tbody></table>`;
}

function renderCohortFacts(cohort) {
  const asset = activeAsset(cohort);
  elements.cohortFactGrid.innerHTML = cohort.success_rates
    .map((fact) => {
      const perAsset = fact.assets[asset] || {};
      const blocks = cohort.conditions
        .map((condition) => {
          const entry = perAsset[condition.condition_id] || {};
          const rate = entry.rate;
          const percent = rate === null || rate === undefined
            ? '—'
            : `${(rate * 100).toFixed(0)}%`;
          const detail =
            entry.successes === null || entry.successes === undefined
              ? 'no runs'
              : `${entry.successes} of ${entry.runs} runs`;
          return (
            `<div class="fact-asset" data-verdict="${escapeHtml(entry.verdict || 'unavailable')}">` +
            `<span class="rate-condition">${escapeHtml(condition.label)}</span>` +
            `<span class="rate-value">${escapeHtml(percent)}</span>` +
            `<span class="rate-detail">${escapeHtml(detail)}</span></div>`
          );
        })
        .join('');
      return (
        `<div class="fact-card"><h3>${escapeHtml(fact.fact)}</h3>` +
        `<p class="fact-expectation">${escapeHtml(fact.expectation)}</p>` +
        blocks +
        `</div>`
      );
    })
    .join('');
}

/** Render one comparison cell: the mean, its interval, and its dispersion. */
function comparisonCell(cell, format) {
  if (!cell) {
    return '<td class="metric-number is-missing">—</td>';
  }
  const mean = escapeHtml(formatValue(cell.mean, format));
  const interval =
    cell.ci_half_width === null || cell.ci_half_width === undefined || cell.count < 2
      ? ''
      : `<span class="cell-interval">± ${escapeHtml(formatValue(cell.ci_half_width, format))}</span>`;
  const parts = [];
  if (cell.cov !== null && cell.cov !== undefined) {
    parts.push(`CoV ${cell.cov.toFixed(3)}`);
  }
  if (cell.count !== null && cell.count !== undefined) {
    parts.push(`n = ${Math.round(cell.count)}`);
  }
  const dispersion = parts.length
    ? `<span class="cell-dispersion">${escapeHtml(parts.join(' · '))}</span>`
    : '';
  return (
    `<td class="metric-number"><span class="cell-mean">${mean}</span>` +
    `${interval}${dispersion}</td>`
  );
}

function renderCohortMetricGroups(cohort) {
  const asset = activeAsset(cohort);
  const headers = cohort.conditions
    .map(
      (condition, index) =>
        `<th><span class="condition-header">${conditionSwatch(index)}` +
        `${escapeHtml(condition.label)}</span></th>`
    )
    .join('');

  elements.cohortMetricSections.innerHTML = cohort.metric_groups
    .map((group) => {
      const rows = group.metrics
        .map((metric) => {
          const perAsset = metric.values[asset] || {};
          const cells = cohort.conditions
            .map((condition) =>
              comparisonCell(perAsset[condition.condition_id], metric.format)
            )
            .join('');
          return (
            `<tr${metric.emphasis ? ' class="is-emphasis"' : ''}>` +
            `<td>${escapeHtml(metric.label)}</td>${cells}</tr>`
          );
        })
        .join('');
      return (
        `<section class="panel"><div class="panel-heading">` +
        `<h2>${escapeHtml(group.title)}</h2></div>` +
        `<p class="fact-expectation">${escapeHtml(group.caption)}</p>` +
        `<div class="table-scroll"><table class="metric-table">` +
        `<thead><tr><th>Metric</th>${headers}</tr></thead>` +
        `<tbody>${rows}</tbody></table></div></section>`
      );
    })
    .join('');
}

/* ------------------------------------------------------- cohort charts */

function drawConvergenceChart(cohort) {
  const target = document.getElementById('chart-convergence');
  const asset = activeAsset(cohort);
  const metric = state.convergenceMetric;
  const series = (cohort.convergence.series || []).filter(
    (entry) => entry.asset === asset && entry.metric === metric
  );

  if (!series.length) {
    Plotly.purge('chart-convergence');
    target.textContent = '';
    elements.convergenceMessage.hidden = false;
    elements.convergenceMessage.textContent =
      'Convergence needs runs whose seeds are recorded; none were found for this selection.';
    return;
  }
  elements.convergenceMessage.hidden = true;

  const traces = [];
  series.forEach((entry) => {
    const index = conditionIndex(cohort, entry.condition_id);
    const colour = conditionColour(index);
    const condition = cohort.conditions[index];
    const upper = entry.running_mean.map((value, position) => {
      const half = entry.ci_half_width[position];
      return value === null || half === null ? null : value + half;
    });
    const lower = entry.running_mean.map((value, position) => {
      const half = entry.ci_half_width[position];
      return value === null || half === null ? null : value - half;
    });
    // The band is drawn first so the running mean sits on top of it.
    traces.push({
      x: entry.seed_count,
      y: upper,
      name: `${condition ? condition.label : entry.condition_id} upper`,
      type: 'scatter',
      mode: 'lines',
      line: { width: 0 },
      hoverinfo: 'skip',
      showlegend: false,
    });
    traces.push({
      x: entry.seed_count,
      y: lower,
      name: `${condition ? condition.label : entry.condition_id} 95% CI`,
      type: 'scatter',
      mode: 'lines',
      line: { width: 0 },
      fill: 'tonexty',
      fillcolor: withAlpha(colour, 0.15),
      hoverinfo: 'skip',
      showlegend: false,
    });
    traces.push({
      x: entry.seed_count,
      y: entry.running_mean,
      name: condition ? condition.label : entry.condition_id,
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: colour, width: 1.8 },
      marker: { color: colour, size: 5 },
    });
  });

  const definition = (cohort.convergence.metrics || []).find((entry) => entry.key === metric);
  drawPlot(
    'chart-convergence',
    traces,
    chartLayout('Seeds accumulated', definition ? definition.label : metric, {
      showlegend: cohort.conditions.length > 1,
    }),
    PLOT_CONFIG
  );
}

/* The cohort charts keep their "no data" text in a sibling element, never in
 * the chart div. Writing into a div that holds a live plot removes Plotly's own
 * DOM while its internal state survives, and Plotly only rebuilds that DOM for
 * an empty graph — so the next redraw lands in detached nodes and the chart
 * goes blank on every metric or market switch. */

function drawSpreadChart(cohort) {
  const target = document.getElementById('chart-spread');
  const asset = activeAsset(cohort);
  const metric = state.spreadMetric;
  const series = (cohort.spread.series || []).filter(
    (entry) => entry.asset === asset && entry.metric === metric
  );

  if (!series.length) {
    Plotly.purge('chart-spread');
    target.textContent = '';
    elements.spreadMessage.hidden = false;
    elements.spreadMessage.textContent = 'No per-seed values for this metric.';
    return;
  }
  elements.spreadMessage.hidden = true;

  const traces = series.map((entry) => {
    const index = conditionIndex(cohort, entry.condition_id);
    const condition = cohort.conditions[index];
    return {
      y: entry.points.map((point) => point.value),
      // Every draw is plotted, not just the summary shape: with a handful of
      // seeds a box plot's quartiles are themselves noise, and the reader
      // needs to see whether one seed carried the condition.
      text: entry.points.map((point) =>
        point.seed === null || point.seed === undefined ? 'seed —' : `seed ${point.seed}`
      ),
      name: condition ? condition.label : entry.condition_id,
      type: 'box',
      boxpoints: 'all',
      jitter: 0.5,
      pointpos: 0,
      marker: { color: conditionColour(index), size: 6 },
      line: { color: conditionColour(index), width: 1.2 },
      fillcolor: withAlpha(conditionColour(index), 0.12),
      hoveron: 'points',
    };
  });

  const definition = (cohort.spread.metrics || []).find((entry) => entry.key === metric);
  drawPlot(
    'chart-spread',
    traces,
    chartLayout('', definition ? definition.label : metric, { showlegend: false }),
    PLOT_CONFIG
  );
}

function drawCohortDistribution(cohort) {
  const target = document.getElementById('chart-cohort-distribution');
  const asset = activeAsset(cohort);
  const entry = cohort.distribution.available
    ? cohort.distribution.assets[asset]
    : null;

  if (!entry) {
    Plotly.purge('chart-cohort-distribution');
    target.textContent = '';
    elements.cohortDistributionMessage.hidden = false;
    elements.cohortDistributionMessage.textContent =
      'Too few returns to estimate a distribution.';
    return;
  }
  elements.cohortDistributionMessage.hidden = true;

  const traces = cohort.conditions
    .map((condition, index) => {
      const density = entry.conditions[condition.condition_id];
      if (!density) return null;
      return {
        x: entry.bin_centre,
        y: density.density,
        name: `${condition.label} (${density.observations.toLocaleString('en-GB')} obs)`,
        type: 'scatter',
        mode: 'lines',
        line: { color: conditionColour(index), width: 1.6, shape: 'spline' },
      };
    })
    .filter(Boolean);

  drawPlot(
    'chart-cohort-distribution',
    traces,
    chartLayout('Log return', 'Density', { showlegend: true }),
    PLOT_CONFIG
  );
}

/** Return a CSS colour with an alpha channel, for chart confidence bands.
 *
 * Plotly needs an rgba string; the stylesheet stores hex. Anything that is not
 * a six-digit hex is returned untouched so a future token change degrades to an
 * opaque fill rather than an invalid colour.
 */
function withAlpha(colour, alpha) {
  const match = /^#([0-9a-f]{6})$/i.exec(String(colour).trim());
  if (!match) return colour;
  const value = parseInt(match[1], 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

/* ------------------------------------------------------------- fan chart */

/**
 * Draw each condition's median price history and the band its seeds stay inside.
 *
 * A mean and an interval say how well a statistic is known; this says where the
 * histories themselves went, which is the question when a crash might be an
 * accident of the draw. With few seeds the band is the full range, and the note
 * under the chart says so — it is a description of the spread, never an interval
 * for the median.
 */
function drawPathsChart(cohort) {
  const paths = cohort.paths || { available: false, series: [], measures: [] };
  const asset = activeAsset(cohort);
  const measure = state.pathMeasure;
  const series = (paths.series || []).filter(
    (entry) => entry.asset === asset && entry.measure === measure
  );

  if (!series.length) {
    Plotly.purge('chart-paths');
    clearTwin('chart-paths');
    elements.pathsMessage.hidden = false;
    elements.pathsMessage.textContent =
      'No price history could be read for this selection and market.';
    return;
  }

  const traces = [];
  series.forEach((entry) => {
    const index = conditionIndex(cohort, entry.condition_id);
    const colour = conditionColour(index);
    const condition = cohort.conditions[index];
    const label = condition ? condition.label : entry.condition_id;
    if (state.showMembers) {
      entry.members.forEach((member) => {
        traces.push({
          x: entry.step,
          y: member,
          type: 'scatter',
          mode: 'lines',
          line: { color: withAlpha(colour, 0.35), width: 0.8 },
          hoverinfo: 'skip',
          showlegend: false,
        });
      });
    }
    // The band is drawn first so the median sits on top of it.
    traces.push({
      x: entry.step,
      y: entry.upper,
      type: 'scatter',
      mode: 'lines',
      line: { width: 0 },
      hoverinfo: 'skip',
      showlegend: false,
    });
    traces.push({
      x: entry.step,
      y: entry.lower,
      type: 'scatter',
      mode: 'lines',
      line: { width: 0 },
      fill: 'tonexty',
      fillcolor: withAlpha(colour, 0.15),
      hoverinfo: 'skip',
      showlegend: false,
    });
    traces.push({
      x: entry.step,
      y: entry.median,
      name: `${label} · median of ${entry.seed_count}`,
      type: 'scatter',
      mode: 'lines',
      line: { color: colour, width: 2 },
    });
  });

  const definition = (paths.measures || []).find((entry) => entry.key === measure);
  const reference = measure === 'indexed_price' ? 100 : 0;
  drawPlot(
    'chart-paths',
    traces,
    chartLayout('Step', definition ? definition.label : measure, {
      height: 380,
      showlegend: true,
      shapes: [
        {
          type: 'line',
          xref: 'paper',
          x0: 0,
          x1: 1,
          yref: 'y',
          y0: reference,
          y1: reference,
          line: { color: cssValue('--border-strong'), width: 1 },
          layer: 'below',
        },
      ],
    }),
    PLOT_CONFIG
  );

  const kinds = new Set(series.map((entry) => entry.band_kind));
  const counts = series.map((entry) => entry.seed_count);
  const shortest = Math.min(...counts);
  elements.pathsMessage.hidden = false;
  elements.pathsMessage.textContent =
    (kinds.has('percentile') && !kinds.has('range')
      ? 'Bands run from the 10th to the 90th percentile of the seeds at each step. '
      : kinds.has('percentile')
        ? 'Bands are the full range across seeds, or the 10th–90th percentile where a condition has ten or more. '
        : `Bands are the full range across seeds (minimum to maximum), because with fewer than ten there are too few paths for percentiles. `) +
    `They describe where the histories went, not how well the median is known` +
    (shortest < 2 ? '; a condition with a single seed has no spread to show.' : '.');

  const unionX = [...new Set(series.flatMap((entry) => entry.step))].sort((a, b) => a - b);
  const columns = [];
  series.forEach((entry) => {
    const condition = cohort.conditions[conditionIndex(cohort, entry.condition_id)];
    const label = condition ? condition.label : entry.condition_id;
    columns.push({ name: `${label} · median`, x: entry.step, y: entry.median });
    columns.push({ name: `${label} · lower`, x: entry.step, y: entry.lower });
    columns.push({ name: `${label} · upper`, x: entry.step, y: entry.upper });
  });
  setTwin('chart-paths', `cohort_${asset}_${measure}`, tableFromSeries('step', unionX, columns));
}

/** Offer the measures the fan chart can draw, and reflect the seeds toggle. */
function renderPathControls(cohort) {
  const measures = ((cohort.paths || {}).measures || []).map((entry) => ({
    value: entry.key,
    label: entry.key === 'indexed_price' ? 'Price (indexed)' : 'Mispricing',
  }));
  state.pathMeasure = measures.length ? measures[0].value : null;
  fillSegmented(elements.pathMeasure, measures, state.pathMeasure);
  elements.pathMembers.setAttribute('aria-pressed', String(state.showMembers));
}

/* ------------------------------------------------- cohort orchestration */

function renderCohortCharts(cohort) {
  drawPathsChart(cohort);
  drawConvergenceChart(cohort);
  drawSpreadChart(cohort);
  drawCohortDistribution(cohort);
}

/** Redraw everything that depends on which market is in focus. */
function renderCohortForAsset(cohort) {
  renderVerdicts(cohort);
  renderCohortFacts(cohort);
  renderCohortMetricGroups(cohort);
  renderCohortCharts(cohort);
}

function renderCohort(cohort) {
  state.cohort = cohort;
  state.mode = 'cohort';
  state.cohortAsset = cohort.assets.names[0];

  const conditions = cohort.condition_count === 1 ? '1 condition' : `${cohort.condition_count} conditions`;
  const seeds = cohort.seed_count === 1 ? '1 seed' : `${cohort.seed_count} seeds`;
  elements.cohortTitle.textContent = `${cohort.run_count} runs · ${conditions}`;
  elements.cohortSummary.textContent = `${seeds} · ${cohort.phase} phase · ${cohort.price_column}`;

  renderConditionLegend(cohort);
  renderCohortAssetLegend(cohort);

  fillSegmented(
    elements.cohortAsset,
    cohort.assets.names.map((name) => ({ value: name, label: name })),
    state.cohortAsset
  );

  const convergenceOptions = (cohort.convergence.metrics || []).map((metric) => ({
    value: metric.key,
    label: metric.label,
  }));
  state.convergenceMetric = convergenceOptions.length ? convergenceOptions[0].value : null;
  fillSegmented(elements.convergenceMetric, convergenceOptions, state.convergenceMetric);

  const spreadOptions = (cohort.spread.metrics || []).map((metric) => ({
    value: metric.key,
    label: metric.label,
  }));
  // Excess kurtosis is the default because it is the stylised fact whose
  // per-seed dispersion is largest, so it is where an outlier seed shows.
  const kurtosis = spreadOptions.find((option) => option.value === 'excess_kurtosis');
  state.spreadMetric = kurtosis
    ? kurtosis.value
    : spreadOptions.length
      ? spreadOptions[0].value
      : null;
  fillSegmented(elements.spreadMetric, spreadOptions, state.spreadMetric);

  renderPathControls(cohort);

  elements.cohortFooter.innerHTML = cohort.notes.map(escapeHtml).join('<br>');

  showView('cohort');

  renderCohortForAsset(cohort);
}

async function loadCohort() {
  const paths = Array.from(state.selectedPaths);
  if (paths.length < 2) return;

  const generation = ++state.requestGeneration;
  showStatus(`Computing diagnostics for ${paths.length} runs…`, false);

  const query = new URLSearchParams();
  paths.forEach((path) => query.append('path', path));
  query.set('phase', state.phase);
  query.set('price_column', state.priceColumn);

  try {
    const cohort = await fetchJson(`/api/cohort?${query.toString()}`);
    if (generation !== state.requestGeneration) return;
    hideStatus();
    renderCohort(cohort);
  } catch (error) {
    if (generation !== state.requestGeneration) return;
    showView('none');
    state.cohort = null;
    showStatus(`Could not compare these runs: ${error.message}`, true);
  }
}

/* ------------------------------------------------------- calibration study */

/** The sidebar line under a study's name. */
function studySummaryText(study) {
  const parts = [];
  if (study.trial_count !== null && study.trial_count !== undefined) {
    parts.push(`${Math.round(study.trial_count).toLocaleString('en-GB')} trials`);
  }
  if (study.best_search_score !== null && study.best_search_score !== undefined) {
    parts.push(`best ${formatValue(study.best_search_score, 'decimal')}`);
  }
  if (study.created_at) parts.push(String(study.created_at).slice(0, 10));
  return parts.join('  ·  ');
}

function renderStudyList() {
  const studies = state.studies;
  elements.studyList.hidden = studies.length === 0;
  if (!studies.length) {
    elements.studyList.innerHTML = '';
    return;
  }
  elements.studyList.innerHTML =
    '<div class="study-heading">Calibration studies</div>' +
    studies
      .map(
        (study) =>
          `<button type="button" class="run-button${study.path === state.selectedStudy ? ' is-selected' : ''}" ` +
          `data-path="${escapeHtml(study.path)}" title="${escapeHtml(study.path)}">` +
          `<span class="run-button-id">${escapeHtml(study.name)}</span>` +
          `<span class="run-button-meta">${escapeHtml(studySummaryText(study))}</span></button>`
      )
      .join('');
}

async function selectStudy(path) {
  state.selectedStudy = path;
  state.selectedPath = null;
  state.mode = 'calibration';
  renderCatalogue();
  renderStudyList();
  showStatus('Reading calibration study…', false);

  const generation = ++state.requestGeneration;
  const query = new URLSearchParams({ path });
  try {
    const view = await fetchJson(`/api/calibration/study?${query.toString()}`);
    if (generation !== state.requestGeneration) return;
    hideStatus();
    renderCalibration(view);
  } catch (error) {
    if (generation !== state.requestGeneration) return;
    showView('none');
    state.calibration = null;
    showStatus(`Could not open this study: ${error.message}`, true);
  }
}

/** Draw every trial's score and the best score reached so far. */
function drawCalibrationProgress(view) {
  const progress = view.progress;
  if (!progress.available) {
    Plotly.purge('chart-calibration-progress');
    clearTwin('chart-calibration-progress');
    elements.calibrationProgressMessage.hidden = false;
    elements.calibrationProgressMessage.textContent = 'This study has no completed search trials yet.';
    return;
  }
  elements.calibrationProgressMessage.hidden = true;

  const traces = [
    {
      x: progress.trial,
      y: progress.score,
      name: 'Trial score',
      type: 'scatter',
      mode: 'markers',
      marker: { size: 5, color: withAlpha(cssValue('--text-faint'), 0.7) },
    },
    {
      x: progress.trial,
      y: progress.best_so_far,
      name: 'Best so far',
      type: 'scatter',
      mode: 'lines',
      line: { color: cssValue('--accent'), width: 2, shape: 'hv' },
    },
  ];
  const selected = view.parameters.selected_trial;
  const position = selected === null || selected === undefined ? -1 : progress.trial.indexOf(selected);
  if (position >= 0) {
    traces.push({
      x: [progress.trial[position]],
      y: [progress.score[position]],
      name: 'Selected candidate',
      type: 'scatter',
      mode: 'markers',
      marker: {
        size: 11,
        color: cssValue('--accent'),
        line: { color: cssValue('--surface'), width: 2 },
      },
    });
  }
  drawPlot(
    'chart-calibration-progress',
    traces,
    chartLayout('Trial', 'Score (lower is better)', { height: 340 }),
    PLOT_CONFIG
  );
  setTwin(
    'chart-calibration-progress',
    `${view.name}_progress`,
    tableFromSeries('trial', progress.trial, [
      { name: 'score', x: progress.trial, y: progress.score },
      { name: 'best_so_far', x: progress.trial, y: progress.best_so_far },
    ])
  );
}

/** Split every trial's score into benchmark distance and stylised-fact penalty. */
function drawCalibrationDecomposition(view) {
  const decomposition = view.decomposition;
  if (!decomposition.available) {
    Plotly.purge('chart-calibration-decomposition');
    clearTwin('chart-calibration-decomposition');
    elements.calibrationLevels.innerHTML = '';
    elements.calibrationDecompositionMessage.hidden = false;
    elements.calibrationDecompositionMessage.textContent = decomposition.identity_holds === false
      ? 'In this study the score is not market distance plus stylised-fact penalty, so it cannot be split.'
      : 'This study has no completed search trials to split.';
    return;
  }
  elements.calibrationDecompositionMessage.hidden = true;

  // Both parts are drawn for each trial, in trial order or ranked by total score.
  const order = decomposition.trial.map((_, index) => index);
  if (state.decompositionOrder === 'score') {
    order.sort(
      (a, b) =>
        decomposition.market_distance[a] + decomposition.stylised_penalty[a] -
        (decomposition.market_distance[b] + decomposition.stylised_penalty[b])
    );
  }
  const x = state.decompositionOrder === 'score' ? order.map((_, rank) => rank + 1) : order.map((i) => decomposition.trial[i]);
  const trialNumbers = order.map((i) => decomposition.trial[i]);
  const distance = order.map((i) => decomposition.market_distance[i]);
  const penalty = order.map((i) => decomposition.stylised_penalty[i]);

  drawPlot(
    'chart-calibration-decomposition',
    [
      {
        x,
        y: distance,
        customdata: trialNumbers,
        name: 'Distance from benchmarks',
        type: 'bar',
        marker: { color: withAlpha(cssValue('--text-faint'), 0.6), line: { width: 0 } },
        hovertemplate: 'trial %{customdata}<br>distance %{y:.3f}<extra></extra>',
      },
      {
        x,
        y: penalty,
        customdata: trialNumbers,
        name: 'Stylised-fact penalty',
        type: 'bar',
        marker: { color: cssValue('--accent'), line: { width: 0 } },
        hovertemplate: 'trial %{customdata}<br>penalty %{y:.3f}<extra></extra>',
      },
    ],
    chartLayout(
      state.decompositionOrder === 'score' ? 'Trials ranked by score (best first)' : 'Trial',
      'Score',
      { height: 320, barmode: 'stack', bargap: 0.15, hovermode: 'closest' }
    ),
    PLOT_CONFIG
  );
  setTwin('chart-calibration-decomposition', `${view.name}_score_decomposition`, {
    columns: ['trial', 'market_distance', 'stylised_penalty'],
    rows: trialNumbers.map((trial, index) => [trial, distance[index], penalty[index]]),
  });

  const perFact = decomposition.penalty_per_fact;
  const total = decomposition.trial.length;
  const rows = decomposition.levels
    .map(
      (level) =>
        `<tr><td class="metric-number">${escapeHtml(formatValue(level.penalty, 'decimal'))}</td>` +
        `<td class="metric-number">${escapeHtml(
          level.failed_facts === null || level.failed_facts === undefined
            ? '—'
            : formatValue(level.failed_facts, 'integer')
        )}</td>` +
        `<td class="metric-number">${escapeHtml(formatValue(level.trials, 'integer'))}</td>` +
        `<td class="metric-number">${escapeHtml(formatValue(level.trials / total, 'percent_fraction'))}</td></tr>`
    )
    .join('');
  elements.calibrationLevels.innerHTML =
    `<table class="metric-table calibration-levels"><caption>Search trials by stylised-fact penalty` +
    (perFact ? ` (${escapeHtml(formatValue(perFact, 'decimal'))} per failed fact)` : '') +
    `</caption><thead><tr><th>Penalty</th><th>Facts failed</th><th>Trials</th><th>Share</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

/** One small chart per searched parameter: its value against the score it earned. */
function renderCalibrationParameters(view) {
  const container = elements.calibrationParameters;
  container.querySelectorAll('.chart').forEach((chart) => Plotly.purge(chart));
  const parameters = view.parameters;
  if (!parameters.available) {
    container.innerHTML = '';
    clearTwin('calibration-parameters');
    elements.calibrationParametersMessage.hidden = false;
    elements.calibrationParametersMessage.textContent = 'No searched parameter varied in this study.';
    return;
  }
  elements.calibrationParametersMessage.hidden = true;

  container.innerHTML = parameters.series
    .map(
      (entry) =>
        `<div class="small-multiple${entry.constant ? ' is-constant' : ''}">` +
        `<h3>${escapeHtml(entry.label)}</h3><div class="chart" id="chart-param-${escapeHtml(entry.key)}"></div></div>`
    )
    .join('');

  // One shared score range, so a parameter that moves the score reads as a
  // slope against the same vertical scale as one that does not.
  const scores = parameters.series[0].score.filter((value) => value !== null);
  const pad = (Math.max(...scores) - Math.min(...scores)) * 0.05 || 1;
  const range = [Math.min(...scores) - pad, Math.max(...scores) + pad];
  const candidates = new Set(parameters.candidate_trials || []);
  const outline = { color: cssValue('--surface'), width: 1.5 };

  parameters.series.forEach((entry) => {
    const candidateIndex = entry.trial.map((trial, index) => (candidates.has(trial) ? index : -1)).filter((i) => i >= 0);
    const selectedIndex = entry.trial.indexOf(parameters.selected_trial);
    const traces = [
      {
        x: entry.value,
        y: entry.score,
        type: 'scatter',
        mode: 'markers',
        showlegend: false,
        marker: { size: 5, color: withAlpha(cssValue('--text-faint'), 0.7) },
        hovertemplate: `${entry.label} %{x:.4g}<br>score %{y:.3f}<extra></extra>`,
      },
    ];
    if (candidateIndex.length) {
      traces.push({
        x: candidateIndex.map((i) => entry.value[i]),
        y: candidateIndex.map((i) => entry.score[i]),
        type: 'scatter',
        mode: 'markers',
        showlegend: false,
        marker: { size: 8, color: 'rgba(0,0,0,0)', line: { color: cssValue('--accent'), width: 1.6 } },
        hovertemplate: `validated candidate<br>${entry.label} %{x:.4g}<br>score %{y:.3f}<extra></extra>`,
      });
    }
    if (selectedIndex >= 0) {
      traces.push({
        x: [entry.value[selectedIndex]],
        y: [entry.score[selectedIndex]],
        type: 'scatter',
        mode: 'markers',
        showlegend: false,
        marker: { size: 10, color: cssValue('--accent'), line: outline },
        hovertemplate: `selected candidate<br>${entry.label} %{x:.4g}<br>score %{y:.3f}<extra></extra>`,
      });
    }
    const layout = baseLayout({
      height: 190,
      margin: { l: 44, r: 8, t: 6, b: 32 },
      hovermode: 'closest',
      showlegend: false,
    });
    layout.xaxis = Object.assign({}, layout.xaxis, { nticks: 4, tickfont: { size: 10 } });
    layout.yaxis = Object.assign({}, layout.yaxis, { range, nticks: 4, tickfont: { size: 10 } });
    drawPlot(`chart-param-${entry.key}`, traces, layout, PLOT_CONFIG);
  });

  const first = parameters.series[0];
  setTwin('calibration-parameters', `${view.name}_parameters`, {
    columns: ['trial', 'score', ...parameters.series.map((entry) => entry.key)],
    rows: first.trial.map((trial, index) => [
      trial,
      first.score[index],
      ...parameters.series.map((entry) => entry.value[index]),
    ]),
  });
}

function renderCalibrationCandidates(view) {
  const candidates = view.candidates;
  if (!candidates.available) {
    elements.calibrationCandidates.innerHTML = '';
    return;
  }
  const headers = candidates.columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join('');
  const rows = candidates.rows
    .map((row) => {
      const cells = candidates.columns
        .map((column) => {
          const value = row[column.key];
          const missing = value === null || value === undefined;
          return (
            `<td class="metric-number${missing ? ' is-missing' : ''}">` +
            `${escapeHtml(formatValue(value, column.format))}</td>`
          );
        })
        .join('');
      return `<tr${row.selected ? ' class="is-emphasis"' : ''}>${cells}</tr>`;
    })
    .join('');
  elements.calibrationCandidates.innerHTML =
    `<table class="metric-table"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
}

/**
 * Draw each validated candidate's score on every validation seed beside the score
 * it earned in the search. The search scored it on one seed; the spread here is
 * how much of that score was the seed.
 */
function drawCalibrationValidation(view) {
  const validation = view.validation;
  if (!validation.available) {
    Plotly.purge('chart-calibration-validation');
    clearTwin('chart-calibration-validation');
    elements.calibrationValidationMessage.hidden = false;
    elements.calibrationValidationMessage.textContent =
      'This study has no validation runs: its candidates were not re-scored on further seeds.';
    return;
  }
  elements.calibrationValidationMessage.hidden = true;

  const selected = view.parameters.selected_trial;
  const label = (entry) => `trial ${entry.trial_number}`;
  const emphasised = validation.candidates.filter((entry) => entry.trial_number === selected);
  const others = validation.candidates.filter((entry) => entry.trial_number !== selected);
  const seedTrace = (entries, colour, name) => ({
    x: entries.flatMap((entry) => entry.score.map(() => label(entry))),
    y: entries.flatMap((entry) => entry.score),
    text: entries.flatMap((entry) => entry.seed.map((seed) => `seed ${seed}`)),
    name,
    type: 'scatter',
    mode: 'markers',
    marker: { size: 8, color: colour },
    hovertemplate: '%{x} · %{text}<br>score %{y:.3f}<extra></extra>',
  });
  const traces = [seedTrace(others, withAlpha(cssValue('--text-faint'), 0.85), 'Validation seeds')];
  if (emphasised.length) traces.push(seedTrace(emphasised, cssValue('--accent'), 'Validation seeds · selected'));
  traces.push({
    x: validation.candidates.map(label),
    y: validation.candidates.map((entry) => entry.search_score),
    name: 'Search score (one seed)',
    type: 'scatter',
    mode: 'markers',
    marker: { symbol: 'diamond', size: 11, color: cssValue('--surface'), line: { color: cssValue('--text'), width: 1.6 } },
    hovertemplate: '%{x} · search<br>score %{y:.3f}<extra></extra>',
  });

  drawPlot(
    'chart-calibration-validation',
    traces,
    chartLayout('Validated candidate', 'Score (lower is better)', {
      height: 320,
      hovermode: 'closest',
      xaxis: { type: 'category' },
    }),
    PLOT_CONFIG
  );
  setTwin('chart-calibration-validation', `${view.name}_validation`, {
    columns: ['trial_number', 'seed', 'score', 'search_score'],
    rows: validation.candidates.flatMap((entry) =>
      entry.score.map((score, index) => [entry.trial_number, entry.seed[index], score, entry.search_score])
    ),
  });
}

function renderCalibration(view) {
  state.calibration = view;
  state.mode = 'calibration';
  elements.calibrationTitle.textContent = view.name;
  elements.calibrationChips.innerHTML = view.chips
    .map(
      (chip) =>
        `<span class="parameter-chip">${escapeHtml(chip.label)} <b>${escapeHtml(chip.value)}</b></span>`
    )
    .join('');
  renderTiles(elements.calibrationMetrics, view.metrics);
  elements.calibrationFooter.innerHTML = view.notes.map(escapeHtml).join('<br>');
  setSegmented(elements.decompositionOrder, state.decompositionOrder);

  showView('calibration');
  drawCalibrationProgress(view);
  drawCalibrationDecomposition(view);
  renderCalibrationParameters(view);
  renderCalibrationCandidates(view);
  drawCalibrationValidation(view);
}

/* --------------------------------------------------------------- toggles */

/** Mark the pressed button of a segmented control. */
function setSegmented(container, value) {
  Array.from(container.querySelectorAll('button')).forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.value === value));
  });
}

function wireSegmented(container, onChange, isReady) {
  const ready = isReady || (() => Boolean(state.view));
  container.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || !button.dataset.value || !ready()) return;
    setSegmented(container, button.dataset.value);
    onChange(button.dataset.value);
  });
}

/* ---------------------------------------------------------- orchestration */

/** Reset the per-run defaults, which depend on how many markets the run has. */
function applyRunDefaults(view) {
  state.priceScale = view.assets.count > 1 ? 'indexed' : 'level';
  state.acfSeries = view.assets.count > 1 ? 'absolute' : 'all';
  state.focusAsset = view.assets.names.includes(view.assets.primary)
    ? view.assets.primary
    : view.assets.names[0];
  setSegmented(elements.priceScale, state.priceScale);
  setSegmented(elements.acfSeries, state.acfSeries);
}

/**
 * Draw the run page from its payload.
 *
 * Kept apart from the defaults so a redraw — after a colour-scheme change, say —
 * leaves the scale, market and rows the reader chose exactly as they set them.
 */
function drawRun(view) {
  state.view = view;

  elements.runId.textContent = view.run_id;
  renderProvenance(view.identity, view);
  renderParameters(view.parameters);
  renderAssetLegend(view.assets);
  renderStylisedFacts(view.stylised_facts, view.assets);
  renderMetricGroups(view.metric_groups, view.assets);
  renderFooter(view);

  showView('run');

  redrawStackScope(view);
  drawDistributionChart(view.return_distribution, view.assets);
  drawAutocorrelationChart(view.autocorrelation, view.assets, state.acfSeries);
  drawCounterpartyChart(view);
  renderCrossAsset(view.cross_asset);
  renderProtagonist(view.protagonist);
  renderAgents(view.agents, view.protagonist);
}

function renderRun(view) {
  applyRunDefaults(view);
  drawRun(view);
}

/** Redraw every view that groups agents, after the grouping switch changes. */
function redrawStrategyViews() {
  if (state.mode !== 'run' || !state.view) return;
  const view = state.view;
  redrawStackScope(view);
  drawCounterpartyChart(view);
  if (view.agents.available) drawAgentWealthChart(view.agents, view.protagonist);
}

async function selectRun(path) {
  state.selectedPath = path;
  state.selectedStudy = null;
  state.mode = 'run';
  renderCatalogue();
  renderStudyList();
  showStatus('Computing diagnostics…', false);

  // Every request carries a generation. A cohort takes seconds and a cached run
  // returns at once, so without this a slow earlier reply could land last and
  // draw over whatever the reader had moved on to.
  const generation = ++state.requestGeneration;
  const query = new URLSearchParams({
    path,
    phase: state.phase,
    price_column: state.priceColumn,
  });
  try {
    const view = await fetchJson(`/api/run?${query.toString()}`);
    if (generation !== state.requestGeneration) return;
    hideStatus();
    renderRun(view);
  } catch (error) {
    if (generation !== state.requestGeneration) return;
    showView('none');
    state.view = null;
    showStatus(`Could not open this run: ${error.message}`, true);
  }
}

/** Re-run whichever view is on screen after a phase or price-column change. */
function refreshActiveView() {
  if (state.mode === 'cohort' && state.cohort) {
    loadCohort();
  } else if (state.selectedPath) {
    selectRun(state.selectedPath);
  }
}

async function initialise() {
  elements.phaseSelect.addEventListener('change', (event) => {
    state.phase = event.target.value;
    refreshActiveView();
  });
  elements.priceColumnSelect.addEventListener('change', (event) => {
    state.priceColumn = event.target.value;
    refreshActiveView();
  });
  elements.runSearch.addEventListener('input', (event) => {
    state.filterText = event.target.value.trim().toLowerCase();
    renderCatalogue();
  });

  // Every control below redraws from the payload already in memory; none
  // refetches, so changing the view never refits a GARCH model.
  elements.strategyGrouping.addEventListener('change', (event) => {
    state.strategyGrouping = event.target.value;
    redrawStrategyViews();
  });
  wireSegmented(elements.priceScale, (value) => {
    state.priceScale = value;
    drawMarketStack(state.view);
  });
  wireSegmented(elements.priceSmoothing, (value) => {
    state.priceSmoothing = Number(value);
    syncSmoothingControls(state.view);
    drawMarketStack(state.view);
    renderSmoothingNote(state.view);
  });
  wireSegmented(elements.priceSmoothingMethod, (value) => {
    state.priceSmoothingMethod = value;
    drawMarketStack(state.view);
    renderSmoothingNote(state.view);
  });
  elements.rawPriceToggle.addEventListener('click', () => {
    if (!state.view) return;
    state.showRawPrice = !state.showRawPrice;
    syncSmoothingControls(state.view);
    drawMarketStack(state.view);
    renderSmoothingNote(state.view);
  });
  wireSegmented(elements.stressDefinition, (value) => {
    state.stressDefinition = value;
    drawMarketStack(state.view);
    renderStressRule(state.view);
    renderStressTable(state.view);
  });
  wireSegmented(elements.focusAsset, (value) => {
    state.focusAsset = value;
    redrawStackScope(state.view);
    drawCounterpartyChart(state.view);
  });
  elements.rowToggles.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-row]');
    if (!button || !state.view) return;
    const key = button.dataset.row;
    if (state.hiddenRows.has(key)) state.hiddenRows.delete(key);
    else state.hiddenRows.add(key);
    button.setAttribute('aria-pressed', String(!state.hiddenRows.has(key)));
    drawMarketStack(state.view);
  });
  wireSegmented(elements.flowMatrixMode, (value) => {
    state.flowMatrixMode = value;
    drawCounterpartyChart(state.view);
  });
  wireSegmented(elements.mapColour, (value) => {
    state.mapColour = value;
    renderSocialMap(state.view.agents.social_map, state.view.protagonist);
  });
  wireSegmented(elements.acfSeries, (value) => {
    state.acfSeries = value;
    drawAutocorrelationChart(state.view.autocorrelation, state.view.assets, value);
  });
  setSegmented(elements.flowMatrixMode, state.flowMatrixMode);
  setSegmented(elements.mapColour, state.mapColour);
  setSegmented(elements.decompositionOrder, state.decompositionOrder);

  // The cohort controls redraw from the payload in memory too, so switching
  // market or metric never refits a GARCH model.
  const cohortReady = () => Boolean(state.cohort);
  wireSegmented(
    elements.cohortAsset,
    (value) => {
      state.cohortAsset = value;
      renderCohortForAsset(state.cohort);
    },
    cohortReady
  );
  wireSegmented(
    elements.convergenceMetric,
    (value) => {
      state.convergenceMetric = value;
      drawConvergenceChart(state.cohort);
    },
    cohortReady
  );
  wireSegmented(
    elements.spreadMetric,
    (value) => {
      state.spreadMetric = value;
      drawSpreadChart(state.cohort);
    },
    cohortReady
  );
  wireSegmented(
    elements.pathMeasure,
    (value) => {
      state.pathMeasure = value;
      drawPathsChart(state.cohort);
    },
    cohortReady
  );
  elements.pathMembers.addEventListener('click', () => {
    state.showMembers = !state.showMembers;
    elements.pathMembers.setAttribute('aria-pressed', String(state.showMembers));
    if (state.cohort) drawPathsChart(state.cohort);
  });

  // The calibration page redraws from its payload as well.
  wireSegmented(
    elements.decompositionOrder,
    (value) => {
      state.decompositionOrder = value;
      drawCalibrationDecomposition(state.calibration);
    },
    () => Boolean(state.calibration)
  );
  elements.studyList.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-path]');
    if (button) selectStudy(button.dataset.path);
  });

  // Chart colours are read from CSS custom properties at draw time, so a theme
  // change after a draw would leave the old scheme's colours on the plots until
  // something else forced a redraw. Redraw from the payload already in memory —
  // this refits nothing.
  const scheme = window.matchMedia('(prefers-color-scheme: dark)');
  const redrawForTheme = () => {
    if (state.mode === 'cohort' && state.cohort) renderCohortForAsset(state.cohort);
    else if (state.mode === 'calibration' && state.calibration) renderCalibration(state.calibration);
    else if (state.view) drawRun(state.view);
  };
  if (typeof scheme.addEventListener === 'function') {
    scheme.addEventListener('change', redrawForTheme);
  }

  elements.cohortCompare.addEventListener('click', loadCohort);
  elements.cohortClear.addEventListener('click', () => {
    state.selectedPaths.clear();
    renderCatalogue();
    if (state.mode === 'cohort') {
      state.mode = 'run';
      state.cohort = null;
      if (state.selectedPath) selectRun(state.selectedPath);
      else showView('placeholder');
    }
  });

  try {
    state.catalogue = await fetchJson('/api/catalogue');
  } catch (error) {
    showStatus(`Could not read the archive: ${error.message}`, true);
    return;
  }

  elements.archiveRoot.textContent = shortenPath(state.catalogue.data_root);
  elements.archiveRoot.title = state.catalogue.data_root;
  renderCatalogue();

  try {
    state.studies = (await fetchJson('/api/calibration')).studies || [];
    renderStudyList();
  } catch (error) {
    /* Calibration studies are optional; the run list stands without them. */
  }

  if (state.catalogue.run_count === 0) {
    elements.placeholder.innerHTML =
      '<h1>No runs found</h1><p>Nothing under <code>' +
      escapeHtml(state.catalogue.data_root) +
      '</code> contains a <code>step_timeseries.csv</code>. Run a simulation with ' +
      '<code>experiment_output_enabled = 1</code>, then reload this page.</p>';
    return;
  }

  // Open the most recent run so the dashboard is useful on load rather than
  // asking for a click before showing anything.
  const lastExperiment = state.catalogue.experiments[state.catalogue.experiments.length - 1];
  const lastRun = lastExperiment.runs[lastExperiment.runs.length - 1];
  selectRun(lastRun.path);
}

initialise();
