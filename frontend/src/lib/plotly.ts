/**
 * Shared Plotly configuration for the NIDE dark scientific theme.
 *
 * All physics plots use log-log axes with exponent-format ticks (the way
 * cross sections are always shown in the literature), recessive hairline
 * grids, and a unified hover crosshair. Colors come from the validated
 * dark-surface palette defined in index.css.
 */
import Plotly from 'plotly.js-dist-min'

export { Plotly }

export const THEME = {
  surface: '#1a1a19',
  page: '#0d0d0d',
  textPrimary: '#ffffff',
  textSecondary: '#c3c2b7',
  textMuted: '#898781',
  gridline: '#2c2c2a',
  baseline: '#383835',
}

export function baseLayout(overrides: Partial<Plotly.Layout> = {}): Partial<Plotly.Layout> {
  return {
    paper_bgcolor: THEME.surface,
    plot_bgcolor: THEME.surface,
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: THEME.textSecondary, size: 12 },
    margin: { l: 70, r: 20, t: 36, b: 52 },
    hovermode: 'x unified',
    hoverlabel: { bgcolor: '#26262425', bordercolor: THEME.baseline, font: { color: THEME.textPrimary } },
    legend: {
      bgcolor: 'rgba(0,0,0,0)',
      font: { color: THEME.textSecondary },
      orientation: 'h',
      y: 1.02,
      yanchor: 'bottom',
    },
    ...overrides,
  }
}

export function logAxis(title: string, overrides: Partial<Plotly.LayoutAxis> = {}): Partial<Plotly.LayoutAxis> {
  return {
    title: { text: title, font: { color: THEME.textSecondary } },
    type: 'log',
    exponentformat: 'power',
    gridcolor: THEME.gridline,
    gridwidth: 1,
    zeroline: false,
    linecolor: THEME.baseline,
    tickcolor: THEME.baseline,
    tickfont: { color: THEME.textMuted },
    ticks: 'outside',
    mirror: true,
    ...overrides,
  }
}

export function linearAxis(title: string, overrides: Partial<Plotly.LayoutAxis> = {}): Partial<Plotly.LayoutAxis> {
  return { ...logAxis(title, overrides), type: 'linear' }
}

/**
 * Export the current plot as a publication-quality PNG (2x scale). The
 * evaluation citations are stamped as a footer annotation before export and
 * removed afterwards, so every exported figure is self-citing.
 */
export async function downloadPng(
  element: HTMLElement,
  filename: string,
  citations: string[],
): Promise<void> {
  const annotation: Partial<Plotly.Annotations> = {
    text: citations.join('<br>'),
    showarrow: false,
    xref: 'paper',
    yref: 'paper',
    x: 0,
    y: -0.14,
    xanchor: 'left',
    yanchor: 'top',
    align: 'left',
    font: { size: 9, color: THEME.textMuted },
  }
  // Plotly's relayout accepts attribute-path keys ('margin.b'); the type
  // definitions only model whole-Layout objects, hence the casts.
  await Plotly.relayout(element, {
    'annotations[0]': annotation,
    'margin.b': 110,
  } as unknown as Partial<Plotly.Layout>)
  try {
    await Plotly.downloadImage(element, {
      format: 'png',
      width: 1400,
      height: 900,
      filename,
    })
  } finally {
    await Plotly.relayout(element, {
      annotations: [],
      'margin.b': 52,
    } as unknown as Partial<Plotly.Layout>)
  }
}
