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
  priceScale: document.getElementById('price-scale'),
  acfSeries: document.getElementById('acf-series'),
  runFooter: document.getElementById('run-footer'),
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
function assetColour(index) {
  return cssValue(`--asset-${(index % 4) + 1}`);
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
    heading.innerHTML = `<span>${escapeHtml(experiment.name)}</span><span>${runs.length}</span>`;
    heading.title = experiment.path;
    group.appendChild(heading);

    runs.forEach((run) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'run-button';
      button.dataset.path = run.path;
      button.classList.toggle('is-selected', run.path === state.selectedPath);
      button.innerHTML =
        `<span class="run-button-id">${escapeHtml(run.run_id)}</span>` +
        `<span class="run-button-meta">${escapeHtml(runSummaryText(run))}</span>`;
      button.addEventListener('click', () => selectRun(run.path));
      group.appendChild(button);
    });

    elements.runList.appendChild(group);
  });

  const total = catalogue.run_count;
  elements.sidebarCount.textContent = state.filterText
    ? `${visibleRuns} of ${total} runs`
    : `${total} runs in ${catalogue.experiment_count} groups`;
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

function renderAgents(agents) {
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
  drawAgentWealthChart(agents);
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
        line: { color: cssValue('--asset-1'), width: 1.3 },
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
        line: { color: cssValue('--asset-2'), width: 1.3 },
      },
    ],
    chartLayout('Step', `Price ratio ${crossAsset.asset_a} / ${crossAsset.asset_b}`, {
      height: 300,
      showlegend: false,
    }),
    PLOT_CONFIG
  );
}

function drawAgentWealthChart(agents) {
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

  Plotly.react(
    'chart-agent-wealth',
    traces,
    chartLayout('Final wealth', 'Density', { height: 300, hovermode: 'closest' }),
    PLOT_CONFIG
  );
}

/* --------------------------------------------------------------- toggles */

/** Mark the pressed button of a segmented control. */
function setSegmented(container, value) {
  Array.from(container.querySelectorAll('button')).forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.value === value));
  });
}

function wireSegmented(container, onChange) {
  container.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || !state.view) return;
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
  renderAgents(view.agents);
}

async function selectRun(path) {
  state.selectedPath = path;
  renderCatalogue();
  showStatus('Computing diagnostics…', false);

  const query = new URLSearchParams({
    path,
    phase: state.phase,
    price_column: state.priceColumn,
  });
  try {
    const view = await fetchJson(`/api/run?${query.toString()}`);
    hideStatus();
    renderRun(view);
  } catch (error) {
    elements.runView.hidden = true;
    elements.placeholder.hidden = true;
    state.view = null;
    showStatus(`Could not open this run: ${error.message}`, true);
  }
}

async function initialise() {
  elements.phaseSelect.addEventListener('change', (event) => {
    state.phase = event.target.value;
    if (state.selectedPath) selectRun(state.selectedPath);
  });
  elements.priceColumnSelect.addEventListener('change', (event) => {
    state.priceColumn = event.target.value;
    if (state.selectedPath) selectRun(state.selectedPath);
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
