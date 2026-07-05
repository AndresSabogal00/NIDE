/**
 * Multi-library comparison panel — NIDE's differentiator.
 *
 * Top subplot: sigma(E) per library on the common grid (log-log).
 * Bottom subplot: percent deviation from the reference library (log-x,
 * linear-y) with the discrepancy threshold drawn as a band.
 * Below: automatic discrepancy summary, per-region statistics, and the
 * derived-quantities comparison table (thermal value, resonance integral,
 * Maxwellian and Watt averages, Westcott g) with the convention of each
 * quantity available on hover.
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  api,
  LIBRARY_COLORS,
  type Comparison,
  type DerivedQuantities,
  type LibraryInfo,
  type NuclideReactions,
} from '../../api/client'
import { displayNuclide, formatEnergy, formatSigma } from '../../lib/format'
import { baseLayout, logAxis, THEME } from '../../lib/plotly'
import { useSelection } from '../../state/SelectionContext'
import PlotlyChart from '../PlotlyChart'
import ExportButtons from '../ExportDialog/ExportButtons'
import { Citations, ErrorNote, Field, NuclideInput, Panel, Select } from '../controls'

export default function ComparisonPanel() {
  const [params, setParams] = useSearchParams()
  const { selection, update } = useSelection()
  const [libraries, setLibraries] = useState<LibraryInfo[]>([])
  const [nuclides, setNuclides] = useState<string[]>([])
  const [reactions, setReactions] = useState<NuclideReactions | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [derived, setDerived] = useState<DerivedQuantities | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [plotEl, setPlotEl] = useState<HTMLDivElement | null>(null)

  // URL param (deep link) > shared selection > default; see SelectionContext.
  const nuclide = params.get('nuclide') ?? selection.nuclide
  const mt = Number(params.get('mt') ?? selection.mt)
  const threshold = Number(params.get('th') ?? selection.thresholdPercent)
  const reference = params.get('ref') ?? selection.referenceLibrary
  // The engine treats the first library as the reference, so order matters.
  const allLibs = [reference, ...['endfb80', 'jeff33', 'jendl5'].filter((l) => l !== reference)]

  useEffect(() => {
    update({ nuclide, mt, thresholdPercent: threshold, referenceLibrary: reference })
  }, [nuclide, mt, threshold, reference]) // eslint-disable-line react-hooks/exhaustive-deps

  const setParam = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set(key, value)
        return next
      },
      { replace: true },
    )

  useEffect(() => {
    api.libraries().then(setLibraries).catch((e) => setError(String(e.message)))
    api.nuclides('endfb80').then(setNuclides).catch(() => {})
  }, [])

  useEffect(() => {
    if (!nuclide) return
    api.reactions(nuclide, 'endfb80').then(setReactions).catch(() => setReactions(null))
  }, [nuclide])

  useEffect(() => {
    if (!nuclide) return
    setLoading(true)
    setError(null)
    Promise.all([
      api.compare(nuclide, mt, allLibs, threshold, '294K'),
      api.derived(nuclide, mt, allLibs, '294K'),
    ])
      .then(([cmp, der]) => {
        setComparison(cmp)
        setDerived(der)
      })
      .catch((e) => {
        setError(String(e.message))
        setComparison(null)
        setDerived(null)
      })
      .finally(() => setLoading(false))
  }, [nuclide, mt, threshold, reference]) // eslint-disable-line react-hooks/exhaustive-deps

  const { traces, layout } = useMemo(() => {
    if (!comparison) return { traces: [] as Plotly.Data[], layout: {} }
    const curves: Plotly.Data[] = Object.entries(comparison.curves).map(([lib, xs]) => ({
      x: comparison.energy_ev,
      y: xs,
      type: 'scattergl',
      mode: 'lines',
      name: libraries.find((l) => l.library_id === lib)?.name ?? lib,
      line: { color: LIBRARY_COLORS[lib], width: 2 },
      hovertemplate: '%{y:.4g} b',
    }))
    const diffs: Plotly.Data[] = Object.entries(comparison.diff_percent).map(([lib, d]) => ({
      x: comparison.energy_ev,
      y: d,
      type: 'scattergl',
      mode: 'lines',
      name: `${libraries.find((l) => l.library_id === lib)?.name ?? lib} vs ref`,
      line: { color: LIBRARY_COLORS[lib], width: 1.5 },
      xaxis: 'x',
      yaxis: 'y2',
      showlegend: false,
      hovertemplate: '%{y:.2f}%',
    }))
    const combinedLayout = baseLayout({
      title: {
        text: `${displayNuclide(nuclide)} — ${comparison.reaction_name}: libraries vs ${
          libraries.find((l) => l.library_id === comparison.reference_library)?.name ??
          comparison.reference_library
        }`,
        font: { color: '#ffffff', size: 15 },
      },
      grid: { rows: 2, columns: 1, subplots: [['xy'], ['xy2']] as never },
      xaxis: logAxis('Incident neutron energy (eV)'),
      yaxis: { ...logAxis('sigma (barns)'), domain: [0.42, 1] },
      yaxis2: {
        title: { text: 'deviation from ref (%)', font: { color: THEME.textSecondary } },
        gridcolor: THEME.gridline,
        zeroline: true,
        zerolinecolor: THEME.baseline,
        linecolor: THEME.baseline,
        tickfont: { color: THEME.textMuted },
        domain: [0, 0.34],
        // Deviations near sharp resonances blow up due to tiny mesh shifts
        // between evaluations (see comparison_engine docstring); clamp the
        // default view to keep the systematic differences readable.
        range: [-Math.max(threshold * 4, 20), Math.max(threshold * 4, 20)],
      },
      shapes: [
        // Threshold band on the deviation subplot.
        {
          type: 'rect',
          xref: 'paper',
          yref: 'y2',
          x0: 0,
          x1: 1,
          y0: -threshold,
          y1: threshold,
          fillcolor: 'rgba(195,194,183,0.07)',
          line: { width: 0 },
        },
        // Above-threshold intervals, widest (most significant) first. Capped:
        // a resonant nuclide can produce hundreds of one-point spikes that
        // would smear into a solid block; the caption states the cap.
        ...[...comparison.discrepancies]
          .sort((a, b) => b.lethargy_width - a.lethargy_width)
          .slice(0, 30)
          .map((d) => ({
            type: 'rect' as const,
            xref: 'x' as const,
            yref: 'y2 domain' as never,
            x0: d.e_min_ev,
            x1: Math.max(d.e_max_ev, d.e_min_ev * 1.001),
            y0: 0,
            y1: 1,
            fillcolor: 'rgba(230,103,103,0.14)',
            line: { width: 0 },
          })),
      ],
      height: 680,
    })
    return { traces: [...curves, ...diffs], layout: combinedLayout }
  }, [comparison, libraries, nuclide, threshold])

  const citations = useMemo(
    () => Object.entries(comparison?.citations ?? {}).map(([, c]) => c),
    [comparison],
  )

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Nuclide">
            <NuclideInput value={nuclide} nuclides={nuclides} onChange={(n) => setParam('nuclide', n)} />
          </Field>
          <Field label="Reaction (MT)">
            <Select
              value={String(mt)}
              onChange={(v) => setParam('mt', v)}
              options={
                reactions?.reactions.map((r) => ({
                  value: String(r.mt),
                  label: `${r.name} · MT=${r.mt}`,
                })) ?? [{ value: String(mt), label: `MT=${mt}` }]
              }
            />
          </Field>
          <Field label="Reference library">
            <Select
              value={reference}
              onChange={(v) => setParam('ref', v)}
              options={[
                { value: 'endfb80', label: 'ENDF/B-VIII.0' },
                { value: 'jeff33', label: 'JEFF-3.3' },
                { value: 'jendl5', label: 'JENDL-5' },
              ]}
            />
          </Field>
          <Field label="Discrepancy threshold (%)">
            <Select
              value={String(threshold)}
              onChange={(v) => setParam('th', v)}
              options={['1', '2', '5', '10', '20'].map((t) => ({ value: t, label: `${t}%` }))}
            />
          </Field>
          <div className="ml-auto pb-1">
            <ExportButtons
              csvUrl={
                comparison
                  ? `/api/export/comparison-csv?nuclide=${nuclide}&mt=${mt}&libraries=${allLibs.join(',')}&threshold=${threshold}`
                  : null
              }
              pngFilename={`nide_compare_${nuclide}_mt${mt}`}
              plotElement={plotEl}
              citations={citations}
            />
          </div>
        </div>
      </Panel>

      <ErrorNote error={error} />
      {comparison && comparison.missing_libraries.length > 0 && (
        <div className="rounded-md border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-muted)]">
          Not available in: {comparison.missing_libraries.join(', ')}
        </div>
      )}

      {comparison && (
        <>
          <Panel>
            <h2 className="mb-2 text-sm font-medium text-[var(--text-primary)]">
              Automatic discrepancy report
            </h2>
            <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
              {comparison.summary.map((line) => (
                <li key={line}>· {line}</li>
              ))}
            </ul>
            {comparison.explanation.length > 0 && (
              <>
                <h3 className="mb-1 mt-3 text-xs font-medium text-[var(--text-primary)]">
                  Reading the comparison
                </h3>
                <ul className="space-y-1 text-xs text-[var(--text-secondary)]">
                  {comparison.explanation.map((line) => (
                    <li key={line}>· {line}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="mt-2 text-[11px] leading-snug text-[var(--text-muted)]">
              Extreme maxima (even several hundred %) usually come from a single very narrow
              resonance where the evaluations place the peak at slightly different energies —
              they do not represent the overall agreement of the region. The median and the
              lethargy coverage are the representative statistics.
            </p>
          </Panel>

          <Panel className={loading ? 'opacity-60' : ''}>
            <PlotlyChart data={traces} layout={layout} onReady={setPlotEl} />
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              Deviation formula: Δ(E) = 100 · (σ_lib(E) − σ_ref(E)) / σ_ref(E), evaluated on
              the union of the libraries' energy grids over their common domain, log-log
              interpolation (lin-lin around zeros). Red shading: intervals where |Δ| exceeds
              the {threshold}% threshold (the {'≤'}30 widest shown); gray band: ±threshold.
            </p>
            <Citations citations={citations} />
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel>
              <h2 className="mb-2 text-sm font-medium">Deviation statistics by energy region</h2>
              <table className="w-full text-xs">
                <thead className="text-[var(--text-muted)]">
                  <tr className="text-left">
                    <th className="py-1 pr-2 font-normal">Library</th>
                    <th className="py-1 pr-2 font-normal">Region</th>
                    <th
                      className="py-1 pr-2 text-right font-normal"
                      title="Typical agreement across the region — the headline statistic"
                    >
                      median |Δ|
                    </th>
                    <th
                      className="py-1 pr-2 text-right font-normal"
                      title={`Share of the region's energy range (in lethargy, i.e. ln E — immune to grid-density bias) where |Δ| exceeds the ${threshold}% threshold`}
                    >
                      &gt;{threshold}% coverage
                    </th>
                    <th
                      className="py-1 pr-2 text-right font-normal"
                      title="Complementary: extreme maxima are usually a single narrow resonance placed at slightly different energies by the evaluations, not regional disagreement"
                    >
                      max |Δ|
                    </th>
                    <th className="py-1 text-right font-normal">at energy</th>
                  </tr>
                </thead>
                <tbody className="text-[var(--text-secondary)] tabular-nums">
                  {comparison.region_stats.map((s) => (
                    <tr
                      key={`${s.library_id}-${s.region}`}
                      className="border-t border-[var(--border)]"
                    >
                      <td className="py-1.5 pr-2">
                        <span
                          className="mr-1.5 inline-block h-2 w-2 rounded-full align-baseline"
                          style={{ backgroundColor: LIBRARY_COLORS[s.library_id] }}
                        />
                        {libraries.find((l) => l.library_id === s.library_id)?.name ?? s.library_id}
                      </td>
                      <td className="py-1.5 pr-2">{s.region}</td>
                      <td
                        className={`py-1.5 pr-2 text-right font-medium ${
                          s.median_abs_diff_percent > threshold
                            ? 'text-[#e66767]'
                            : 'text-[var(--text-primary)]'
                        }`}
                      >
                        {s.median_abs_diff_percent.toFixed(2)}%
                      </td>
                      <td className="py-1.5 pr-2 text-right">
                        {(100 * s.lethargy_fraction_above).toFixed(1)}%
                      </td>
                      <td className="py-1.5 pr-2 text-right text-[var(--text-muted)]">
                        {s.max_abs_diff_percent.toFixed(1)}%
                      </td>
                      <td className="py-1.5 text-right text-[var(--text-muted)]">
                        {formatEnergy(s.energy_at_max_ev)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            {derived && (
              <Panel>
                <h2 className="mb-2 text-sm font-medium">
                  Derived quantities at {derived.temperature}
                </h2>
                <table className="w-full text-xs">
                  <thead className="text-[var(--text-muted)]">
                    <tr className="text-left">
                      <th className="py-1 pr-2 font-normal">Quantity</th>
                      {derived.results.map((r) => (
                        <th key={r.library_id} className="py-1 pr-2 text-right font-normal">
                          <span
                            className="mr-1.5 inline-block h-2 w-2 rounded-full align-baseline"
                            style={{ backgroundColor: LIBRARY_COLORS[r.library_id] }}
                          />
                          {r.library_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="text-[var(--text-secondary)] tabular-nums">
                    {(
                      [
                        ['thermal_xs_barns', 'Thermal (2200 m/s) [b]'],
                        ['resonance_integral_barns', 'Resonance integral [b]'],
                        ['maxwellian_avg_barns', 'Maxwellian avg (293.6 K) [b]'],
                        ['watt_avg_barns', 'Watt spectrum avg [b]'],
                        ['westcott_g_factor', 'Westcott g-factor'],
                      ] as const
                    ).map(([key, label]) => (
                      <tr key={key} className="border-t border-[var(--border)]">
                        <td className="py-1.5 pr-2" title={derived.definitions[key]}>
                          {label}
                        </td>
                        {derived.results.map((r) => (
                          <td key={r.library_id} className="py-1.5 pr-2 text-right">
                            {formatSigma(r[key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-[11px] text-[var(--text-muted)]">
                  Hover a quantity for its definition and convention. Conventions: Cd cutoff 0.5 eV;
                  Watt spectrum a = 0.988 MeV, b = 2.249 MeV⁻¹ (U-235 thermal, ENDF-102).
                </p>
              </Panel>
            )}
          </div>
        </>
      )}
    </div>
  )
}
