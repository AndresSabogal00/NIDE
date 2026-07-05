/**
 * Fission product yields: the classic double-humped mass-yield curve.
 * Yields vs mass number A (log y), one trace per incident energy
 * (thermal / fast / 14 MeV), with independent vs cumulative toggle and an
 * alternative by-Z view. Same fixed palette order as everywhere else:
 * energies are the series here (thermal=blue, fast=aqua, 14 MeV=yellow).
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type FissionYields } from '../../api/client'
import { displayNuclide } from '../../lib/format'
import { useSelection } from '../../state/SelectionContext'
import { baseLayout, linearAxis, logAxis } from '../../lib/plotly'
import PlotlyChart from '../PlotlyChart'
import ExportButtons from '../ExportDialog/ExportButtons'
import { Citations, ErrorNote, Field, Panel, Select } from '../controls'

const ENERGY_COLORS: Record<string, string> = {
  thermal: '#3987e5',
  fast: '#199e70',
  '14MeV': '#c98500',
}

export default function FissionYieldsView() {
  const [params, setParams] = useSearchParams()
  const { selection, update } = useSelection()
  const [systems, setSystems] = useState<string[]>([])
  const [yields, setYields] = useState<FissionYields | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [plotEl, setPlotEl] = useState<HTMLDivElement | null>(null)

  // Follow the shared nuclide only when it actually has a yield evaluation
  // (only ~30 fissioning systems do); otherwise keep the local default
  // WITHOUT overwriting the shared selection — a user browsing Th-227
  // cross sections must not lose it by visiting this view.
  const sharedIsFissionable = systems.length === 0 || systems.includes(selection.nuclide)
  const nuclide =
    params.get('nuclide') ?? (sharedIsFissionable ? selection.nuclide : 'U235')
  const yieldType = params.get('type') ?? 'cumulative'
  const axis = params.get('axis') ?? 'A'

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
    api.fissionYieldNuclides().then(setSystems).catch((e) => setError(String(e.message)))
  }, [])

  useEffect(() => {
    // Wait for the fissionable-systems list unless the URL pins a nuclide
    // explicitly: avoids a transient 404 for non-fissionable shared nuclides.
    if (!nuclide || (systems.length === 0 && !params.get('nuclide'))) return
    setError(null)
    api
      .fissionYields(nuclide, yieldType)
      .then(setYields)
      .catch((e) => {
        setError(String(e.message))
        setYields(null)
      })
  }, [nuclide, yieldType, systems.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const { traces, layout } = useMemo(() => {
    if (!yields) return { traces: [] as Plotly.Data[], layout: {} }
    const byKey = axis === 'A' ? 'by_mass_number' : 'by_atomic_number'
    const data: Plotly.Data[] = yields.sets.map((set) => {
      const entries = Object.entries(set[byKey]).map(([k, v]) => [Number(k), v] as const)
      entries.sort((a, b) => a[0] - b[0])
      return {
        x: entries.map(([k]) => k),
        y: entries.map(([, v]) => v),
        type: 'scatter',
        mode: 'lines+markers',
        name: `${set.energy_label} (${set.energy_label === 'thermal' ? '0.0253 eV' : set.energy_label === 'fast' ? '500 keV' : '14 MeV'})`,
        line: { color: ENERGY_COLORS[set.energy_label] ?? '#898781', width: 2 },
        marker: { size: 4 },
        hovertemplate: `${axis}=%{x} · %{y:.3e}`,
      }
    })
    return {
      traces: data,
      layout: baseLayout({
        title: {
          text: `${displayNuclide(nuclide)}(n,f) ${yieldType} yields by ${axis === 'A' ? 'mass' : 'atomic'} number`,
          font: { color: '#ffffff', size: 15 },
        },
        xaxis: linearAxis(axis === 'A' ? 'Mass number A' : 'Atomic number Z'),
        yaxis: logAxis('Yield per fission'),
        height: 560,
      }),
    }
  }, [yields, axis, nuclide, yieldType])

  const citations = yields
    ? [
        `${yields.source}. D.A. Brown et al., Nucl. Data Sheets 148 (2018) 1-142.`,
        'T.R. England, B.F. Rider, LA-UR-94-3106 (1994).',
      ]
    : []

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Fissioning nuclide">
            <Select
              value={nuclide}
              onChange={(v) => {
                setParam('nuclide', v)
                // Explicit user choice: propagate to the shared selection so
                // the other views follow (all yield systems are also
                // transport nuclides).
                update({ nuclide: v })
              }}
              options={systems.map((s) => ({ value: s, label: displayNuclide(s) }))}
            />
          </Field>
          <Field label="Yield type">
            <Select
              value={yieldType}
              onChange={(v) => setParam('type', v)}
              options={[
                { value: 'cumulative', label: 'Cumulative (chain yields)' },
                { value: 'independent', label: 'Independent (prompt)' },
              ]}
            />
          </Field>
          <Field label="Aggregate by">
            <Select
              value={axis}
              onChange={(v) => setParam('axis', v)}
              options={[
                { value: 'A', label: 'Mass number A' },
                { value: 'Z', label: 'Atomic number Z' },
              ]}
            />
          </Field>
          <div className="ml-auto pb-1">
            <ExportButtons
              csvUrl={yields ? `/api/export/yields-csv?nuclide=${nuclide}&yield_type=${yieldType}` : null}
              pngFilename={`nide_yields_${nuclide}_${yieldType}`}
              plotElement={plotEl}
              citations={citations}
            />
          </div>
        </div>
      </Panel>

      <ErrorNote error={error} />

      {yields && (
        <>
          <Panel>
            <PlotlyChart data={traces} layout={layout} onReady={setPlotEl} />
            <Citations citations={citations} />
          </Panel>

          <Panel>
            <h2 className="mb-2 text-sm font-medium">
              Highest-yield products ({yields.sets[0]?.energy_label})
            </h2>
            <div className="grid grid-cols-2 gap-x-8 md:grid-cols-4">
              {(yields.sets[0]?.top_products ?? []).map(([product, value]) => (
                <div
                  key={product}
                  className="flex justify-between border-t border-[var(--border)] py-1 text-xs text-[var(--text-secondary)]"
                >
                  <span>{displayNuclide(product)}</span>
                  <span className="tabular-nums">{(value * 100).toFixed(2)}%</span>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
