/* Client for the BABM market-statistics dashboard.
 *
 * The browser holds no analysis logic. Every statistic on the page is computed
 * server-side by `abm_analysis.statistics`, so a number read here is the same
 * number the static report would print. This file selects a run, formats the
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
    return;
  }

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
      return `<tr><td>${escapeHtml(row.strategy)}</td>${cells}</tr>`;
    })
    .join('');

  elements.agentTable.innerHTML =
    `<table class="agent-table"><thead><tr><th>Strategy</th>${headers}</tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
  drawAgentWealthChart(agents, protagonist);
}

function renderProtagonist(protagonist) {
  elements.protagonistMessage.hidden = !protagonist.message;
  elements.protagonistMessage.textContent = protagonist.message || '';

  if (!protagonist.available) {
    elements.protagonistIdentity.innerHTML = '';
    elements.protagonistMetrics.innerHTML = '';
    Plotly.purge('chart-protagonist-wealth');
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

const PLOT_CONFIG = { displayModeBar: false, responsive: true };

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

function drawPriceChart(series, assets, scale) {
  const indexed = scale === 'indexed';
  const traces = [];
  assets.names.forEach((name, index) => {
    const track = series.assets[name];
    if (!track) return;
    const colour = assetColour(index);
    // Both lines are divided by the *market* base price. Indexing the
    // fundamental by its own first value would force the opening mispricing to
    // zero and misdraw the gap the chart exists to show.
    const base = indexed ? track.base_price : null;
    traces.push({
      x: series.step,
      y: indexed ? indexTrack(track.price, base) : track.price,
      name: assets.count > 1 ? `${name} price` : 'Market price',
      legendgroup: name,
      type: 'scatter',
      mode: 'lines',
      line: { color: colour, width: 1.4 },
    });
    if (track.fundamental && track.fundamental.length) {
      traces.push({
        x: series.step,
        y: indexed ? indexTrack(track.fundamental, base) : track.fundamental,
        name: assets.count > 1 ? `${name} fundamental` : 'Fundamental value',
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
      });
    }
  });
  Plotly.react(
    'chart-price',
    traces,
    chartLayout('Step', indexed ? 'Index (phase start = 100)' : 'Price'),
    PLOT_CONFIG
  );
}

function drawReturnChart(series, assets) {
  const traces = assets.names
    .filter((name) => series.assets[name])
    .map((name, index) => ({
      x: series.step,
      y: series.assets[name].log_return,
      name: assets.count > 1 ? name : 'Log return',
      type: 'scatter',
      mode: 'lines',
      opacity: assets.count > 1 ? 0.75 : 1,
      line: {
        color: assets.count > 1 ? assetColour(index) : cssValue('--series-returns'),
        width: 0.9,
      },
    }));
  Plotly.react(
    'chart-returns',
    traces,
    chartLayout('Step', 'log(Pt / Pt-1)', {
      height: 260,
      showlegend: assets.count > 1,
    }),
    PLOT_CONFIG
  );
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

  Plotly.react(
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
  Plotly.react('chart-autocorrelation', traces, layout, PLOT_CONFIG);
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

  Plotly.react(
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

  Plotly.react(
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

  const single = distribution.strategies.length === 1;
  const traces = distribution.strategies.map((entry, index) => ({
    x: distribution.bin_centre,
    y: entry.density,
    name: `${entry.strategy} (${entry.count})`,
    type: 'scatter',
    mode: 'lines',
    fill: single ? 'tozeroy' : 'none',
    fillcolor: single ? 'rgba(47, 93, 138, 0.18)' : undefined,
    line: { color: assetColour(index), width: 1.6 },
  }));

  const layout = chartLayout('Final wealth', 'Density', {
    height: 300,
    hovermode: 'closest',
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

  Plotly.react('chart-agent-wealth', traces, layout, PLOT_CONFIG);
}

/**
 * Draw the protagonist's wealth path against the population he traded in.
 *
 * His wealth alone cannot separate an investor who traded well from one who
 * held a rising asset, so the median and mean are drawn beside it and his
 * percentile rank runs on a second axis: a flat rank under a rising wealth line
 * means the whole market rose, and a rising rank means he gained on it.
 */
function drawProtagonistWealthChart(trajectory) {
  const target = document.getElementById('chart-protagonist-wealth');
  if (!trajectory || !trajectory.available) {
    Plotly.purge('chart-protagonist-wealth');
    target.textContent = '';
    return;
  }

  const series = trajectory.series || {};
  const traces = [];
  if (series.wealth) {
    traces.push({
      x: trajectory.step,
      y: series.wealth,
      name: 'Protagonist wealth',
      type: 'scatter',
      mode: 'lines',
      line: { color: cssValue('--protagonist'), width: 2 },
    });
  }
  if (series.population_median_wealth) {
    traces.push({
      x: trajectory.step,
      y: series.population_median_wealth,
      name: 'Population median',
      type: 'scatter',
      mode: 'lines',
      line: { color: assetColour(0), width: 1.6 },
    });
  }
  if (series.population_mean_wealth) {
    traces.push({
      x: trajectory.step,
      y: series.population_mean_wealth,
      name: 'Population mean',
      type: 'scatter',
      mode: 'lines',
      line: { color: assetColour(1), width: 1.2, dash: 'dot' },
    });
  }
  if (series.wealth_percentile_rank) {
    traces.push({
      x: trajectory.step,
      y: series.wealth_percentile_rank,
      name: 'Percentile rank',
      type: 'scatter',
      mode: 'lines',
      yaxis: 'y2',
      line: { color: cssValue('--text-faint'), width: 1.2 },
    });
  }

  if (!traces.length) {
    Plotly.purge('chart-protagonist-wealth');
    target.textContent = '';
    return;
  }

  const layout = chartLayout('Step', 'Wealth', { height: 340 });
  layout.yaxis2 = {
    title: { text: 'Percentile rank', standoff: 8 },
    overlaying: 'y',
    side: 'right',
    range: [0, 1],
    gridcolor: 'rgba(0,0,0,0)',
    zerolinecolor: cssValue('--border'),
    linecolor: cssValue('--border'),
  };
  layout.margin = { l: 62, r: 62, t: 10, b: 44 };

  Plotly.react('chart-protagonist-wealth', traces, layout, PLOT_CONFIG);
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
  Plotly.react(
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
  Plotly.react(
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

  Plotly.react(
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

/* ------------------------------------------------- cohort orchestration */

function renderCohortCharts(cohort) {
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

  elements.cohortFooter.innerHTML = cohort.notes.map(escapeHtml).join('<br>');

  elements.placeholder.hidden = true;
  elements.runView.hidden = true;
  elements.cohortView.hidden = false;

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
    elements.cohortView.hidden = true;
    elements.runView.hidden = true;
    elements.placeholder.hidden = true;
    state.cohort = null;
    showStatus(`Could not compare these runs: ${error.message}`, true);
  }
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

function renderRun(view) {
  state.view = view;
  // Defaults depend on how many markets the run has, so they reset per run.
  state.priceScale = view.assets.count > 1 ? 'indexed' : 'level';
  state.acfSeries = view.assets.count > 1 ? 'absolute' : 'all';
  setSegmented(elements.priceScale, state.priceScale);
  setSegmented(elements.acfSeries, state.acfSeries);

  elements.runId.textContent = view.run_id;
  renderProvenance(view.identity, view);
  renderParameters(view.parameters);
  renderAssetLegend(view.assets);
  renderStylisedFacts(view.stylised_facts, view.assets);
  renderMetricGroups(view.metric_groups, view.assets);
  renderFooter(view);

  elements.placeholder.hidden = true;
  elements.runView.hidden = false;

  drawPriceChart(view.series, view.assets, state.priceScale);
  drawReturnChart(view.series, view.assets);
  drawDistributionChart(view.return_distribution, view.assets);
  drawAutocorrelationChart(view.autocorrelation, view.assets, state.acfSeries);
  renderCrossAsset(view.cross_asset);
  renderProtagonist(view.protagonist);
  renderAgents(view.agents, view.protagonist);
}

async function selectRun(path) {
  state.selectedPath = path;
  state.mode = 'run';
  renderCatalogue();
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
    elements.cohortView.hidden = true;
    renderRun(view);
  } catch (error) {
    if (generation !== state.requestGeneration) return;
    elements.runView.hidden = true;
    elements.cohortView.hidden = true;
    elements.placeholder.hidden = true;
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

  // Both toggles redraw from the payload already in memory; neither refetches,
  // so changing the view never refits a GARCH model.
  wireSegmented(elements.priceScale, (value) => {
    state.priceScale = value;
    drawPriceChart(state.view.series, state.view.assets, value);
  });
  wireSegmented(elements.acfSeries, (value) => {
    state.acfSeries = value;
    drawAutocorrelationChart(state.view.autocorrelation, state.view.assets, value);
  });

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

  // Chart colours are read from CSS custom properties at draw time, so a theme
  // change after a draw would leave the old scheme's colours on the plots until
  // something else forced a redraw. Redraw from the payload already in memory —
  // this refits nothing.
  const scheme = window.matchMedia('(prefers-color-scheme: dark)');
  const redrawForTheme = () => {
    if (state.mode === 'cohort' && state.cohort) renderCohortForAsset(state.cohort);
    else if (state.view) renderRun(state.view);
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
      elements.cohortView.hidden = true;
      if (state.selectedPath) selectRun(state.selectedPath);
      else elements.placeholder.hidden = false;
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
