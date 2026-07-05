/**
 * Cross-section viewer: interactive log-log sigma(E) plot for one nuclide
 * and reaction across any subset of libraries, with optional EXFOR
 * experimental overlay (each dataset labeled author+year in the legend).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  api,
  EXFOR_COLOR,
  EXFOR_SYMBOLS,
  LIBRARY_COLORS,
  type ExforResponse,
  type LibraryInfo,
  type NuclideReactions,
  type XSCurve,
} from '../../api/client'
import { displayNuclide } from '../../lib/format'
import { baseLayout, logAxis } from '../../lib/plotly'
import PlotlyChart from '../PlotlyChart'
import ExportButtons from '../ExportDialog/ExportButtons'
import { Citations, ErrorNote, Field, LibraryToggles, NuclideInput, Panel, Select } from '../controls'

export default function XSViewer() {
  const [params, setParams] = useSearchParams()
  const [libraries, setLibraries] = useState<LibraryInfo[]>([])
  const [nuclides, setNuclides] = useState<string[]>([])
  const [reactions, setReactions] = useState<NuclideReactions | null>(null)
  const [curves, setCurves] = useState<XSCurve[]>([])
  const [exfor, setExfor] = useState<ExforResponse | null>(null)
  const [showExfor, setShowExfor] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [plotEl, setPlotEl] = useState<HTMLDivElement | null>(null)

  const nuclide = params.get('nuclide') ?? 'U235'
  const mt = Number(params.get('mt') ?? 18)
  const temperature = params.get('T') ?? '294K'
  const selectedLibs = (params.get('libs') ?? 'endfb80').split(',').filter(Boolean)

  const setParam = useCallback(
    (key: string, value: string) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set(key, value)
          return next
        },
        { replace: true },
      ),
    [setParams],
  )

  useEffect(() => {
    api.libraries().then(setLibraries).catch((e) => setError(String(e.message)))
    api.nuclides('endfb80').then(setNuclides).catch(() => {})
  }, [])

  // Reaction list follows the nuclide (from the first selected library).
  useEffect(() => {
    if (!nuclide) return
    api
      .reactions(nuclide, selectedLibs[0] ?? 'endfb80')
      .then(setReactions)
      .catch(() => setReactions(null))
  }, [nuclide, selectedLibs[0]]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch one curve per selected library; missing combinations are dropped
  // silently per-library (a nuclide may exist in ENDF/B but not JEFF).
  useEffect(() => {
    if (!nuclide || !selectedLibs.length) return
    setLoading(true)
    setError(null)
    Promise.allSettled(selectedLibs.map((lib) => api.xs(nuclide, mt, lib, temperature)))
      .then((results) => {
        const ok = results.filter((r) => r.status === 'fulfilled').map((r) => r.value)
        setCurves(ok)
        if (!ok.length) {
          const firstError = results.find((r) => r.status === 'rejected') as
            | PromiseRejectedResult
            | undefined
          setError(firstError ? String(firstError.reason.message) : 'No data')
        }
      })
      .finally(() => setLoading(false))
  }, [nuclide, mt, temperature, params.get('libs')]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!showExfor || !nuclide) {
      setExfor(null)
      return
    }
    api
      .exfor(nuclide, mt)
      .then(setExfor)
      .catch(() =>
        setExfor({ nuclide, mt, available: false, message: 'EXFOR service unreachable', datasets: [] }),
      )
  }, [showExfor, nuclide, mt])

  const traces = useMemo<Plotly.Data[]>(() => {
    const evaluated: Plotly.Data[] = curves.map((c) => ({
      x: c.energy_ev,
      y: c.xs_barns,
      type: 'scattergl',
      mode: 'lines',
      name: c.library_name,
      line: { color: LIBRARY_COLORS[c.library_id] ?? '#3987e5', width: 2 },
      hovertemplate: '%{y:.4g} b @ %{x:.4g} eV',
    }))
    const experimental: Plotly.Data[] = (exfor?.datasets ?? []).map((d, i) => ({
      x: d.points.map((p) => p.energy_ev),
      y: d.points.map((p) => p.xs_barns),
      error_y: d.points.some((p) => p.dxs_barns != null)
        ? {
            type: 'data' as const,
            array: d.points.map((p) => p.dxs_barns ?? 0),
            color: EXFOR_COLOR,
            thickness: 1,
            width: 0,
          }
        : undefined,
      type: 'scattergl',
      mode: 'markers',
      name: `${d.author} (${d.year ?? '?'}) · EXFOR ${d.entry}`,
      marker: {
        color: EXFOR_COLOR,
        symbol: EXFOR_SYMBOLS[i % EXFOR_SYMBOLS.length],
        size: 6,
        line: { width: 1 },
      },
      hovertemplate: `%{y:.4g} b @ %{x:.4g} eV<br>${d.author} ${d.year ?? ''}`,
    }))
    return [...evaluated, ...experimental]
  }, [curves, exfor])

  const layout = useMemo(
    () =>
      baseLayout({
        title: {
          text: `${displayNuclide(nuclide)} — ${curves[0]?.reaction_name ?? `MT=${mt}`} at ${temperature}`,
          font: { color: '#ffffff', size: 15 },
        },
        xaxis: logAxis('Incident neutron energy (eV)'),
        yaxis: logAxis('Cross section (barns)'),
        height: 560,
      }),
    [nuclide, mt, temperature, curves],
  )

  const citations = useMemo(() => {
    const list = curves.map((c) => `${c.library_name}: ${c.citation}`)
    if (exfor?.datasets.length) {
      list.push('Experimental: EXFOR database, IAEA Nuclear Data Section (nds.iaea.org/exfor).')
    }
    return [...new Set(list)]
  }, [curves, exfor])

  const csvUrl = curves.length
    ? `/api/export/csv?nuclide=${nuclide}&mt=${mt}&libraries=${selectedLibs.join(',')}&temperature=${temperature}`
    : null

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
                  label: `${r.name} · MT=${r.mt}${r.redundant ? ' (summed)' : ''}`,
                })) ?? [{ value: String(mt), label: `MT=${mt}` }]
              }
            />
          </Field>
          <Field label="Temperature">
            <Select
              value={temperature}
              onChange={(v) => setParam('T', v)}
              options={(reactions?.temperatures ?? ['294K']).map((t) => ({ value: t, label: t }))}
            />
          </Field>
          <Field label="Libraries">
            <LibraryToggles
              available={libraries}
              selected={selectedLibs}
              colors={LIBRARY_COLORS}
              onChange={(libs) => setParam('libs', libs.join(','))}
            />
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={showExfor}
              onChange={(e) => setShowExfor(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            EXFOR overlay
          </label>
          <div className="ml-auto pb-1">
            <ExportButtons
              csvUrl={csvUrl}
              pngFilename={`nide_${nuclide}_mt${mt}`}
              plotElement={plotEl}
              citations={citations}
            />
          </div>
        </div>
      </Panel>

      <ErrorNote error={error} />
      {exfor && !exfor.available && (
        <div className="rounded-md border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-muted)]">
          EXFOR overlay unavailable: {exfor.message ?? 'no experimental data found'} — evaluated
          curves are unaffected.
        </div>
      )}

      <Panel className={loading ? 'opacity-60' : ''}>
        <PlotlyChart data={traces} layout={layout} onReady={setPlotEl} />
        {curves[0]?.downsampled && (
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            Curve decimated to ~{curves[0].energy_ev.length.toLocaleString()} of{' '}
            {curves[0].n_points_full.toLocaleString()} evaluation grid points for display
            (peak-preserving LTTB); CSV export contains the full grid.
          </p>
        )}
        <Citations citations={citations} />
      </Panel>
    </div>
  )
}
