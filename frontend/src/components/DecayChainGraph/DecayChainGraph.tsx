/**
 * Decay chain viewer: directed graph (Cytoscape.js) from a starting nuclide
 * down to stability. Nodes carry half-life; edges carry decay mode and
 * branching ratio. Node positions use the physical (N, Z) layout — the same
 * coordinates as the chart of nuclides — so alpha steps go down-left and
 * beta-minus steps go up-left, exactly like the wall-chart diagrams.
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import cytoscape from 'cytoscape'
import { api, type DecayChain, type DecayInfo } from '../../api/client'
import { displayNuclide } from '../../lib/format'
import { useSelection } from '../../state/SelectionContext'
import { ErrorNote, Field, NuclideInput, Panel, Select } from '../controls'

const MODE_EDGE_COLORS: Record<string, string> = {
  'beta-': '#3987e5',
  alpha: '#c98500',
  ec: '#199e70',
  'ec/beta+': '#199e70',
  'beta+': '#199e70',
  it: '#d55181',
  sf: '#9085e9',
}

export default function DecayChainGraph() {
  const [params, setParams] = useSearchParams()
  const { selection, update } = useSelection()
  const containerRef = useRef<HTMLDivElement>(null)
  const [nuclides, setNuclides] = useState<string[]>([])
  const [chain, setChain] = useState<DecayChain | null>(null)
  const [info, setInfo] = useState<DecayInfo | null>(null)
  const [selectedInfo, setSelectedInfo] = useState<DecayInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  // URL param (deep link) > shared selection; minBr is view-specific.
  const nuclide = params.get('nuclide') ?? selection.nuclide
  const minBr = params.get('minbr') ?? '0.0001'

  useEffect(() => {
    update({ nuclide })
  }, [nuclide]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Any nuclide with decay data is a valid start; offer the transport-
    // library list plus common series heads as suggestions.
    api.nuclides('endfb80').then(setNuclides).catch(() => {})
  }, [])

  useEffect(() => {
    if (!nuclide) return
    setError(null)
    Promise.all([api.decayChain(nuclide, Number(minBr)), api.decayInfo(nuclide)])
      .then(([c, i]) => {
        setChain(c)
        setInfo(i)
        setSelectedInfo(i)
      })
      .catch((e) => {
        setError(String(e.message))
        setChain(null)
      })
  }, [nuclide, minBr])

  useEffect(() => {
    if (!chain || !containerRef.current) return
    // (N, Z) preset layout: x = N (neutrons, grows right), y = -Z so
    // heavier elements sit higher, matching the chart of nuclides.
    const SCALE = 46
    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...chain.nodes.map((n) => ({
          data: n.data,
          position: {
            x: ((n.data.a as number) - (n.data.z as number)) * SCALE,
            y: -(n.data.z as number) * SCALE * 1.4,
          },
        })),
        ...chain.edges,
      ],
      layout: { name: 'preset', fit: true, padding: 30 },
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(id)',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '9px',
            color: '#0d0d0d',
            'background-color': '#c3c2b7',
            width: 40,
            height: 26,
            shape: 'round-rectangle',
          },
        },
        {
          selector: 'node[?stable]',
          style: { 'background-color': '#e8e7e0', 'border-width': 2, 'border-color': '#ffffff' },
        },
        {
          selector: 'node[!stable]',
          style: { 'background-color': '#6da7ec' },
        },
        {
          selector: 'edge',
          style: {
            width: 'data(width)' as never,
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'line-color': 'data(color)' as never,
            'target-arrow-color': 'data(color)' as never,
            label: 'data(label)',
            'font-size': '8px',
            color: '#c3c2b7',
            'text-rotation': 'autorotate',
            'text-background-color': '#1a1a19',
            'text-background-opacity': 0.85,
            'text-background-padding': '1px',
          },
        },
      ],
      wheelSensitivity: 0.2,
    })
    // Edge cosmetics computed client-side: color per mode, width and label
    // reflect the branching ratio so minor branches read as minor.
    cy.edges().forEach((edge) => {
      const mode = String(edge.data('mode'))
      const br = Number(edge.data('branching_ratio'))
      edge.data('color', MODE_EDGE_COLORS[mode] ?? '#898781')
      edge.data('width', Math.max(1, 3.5 * Math.sqrt(br)))
      edge.data(
        'label',
        `${mode}${br < 0.9995 ? ` ${br < 0.001 ? br.toExponential(1) : (br * 100).toFixed(br > 0.1 ? 1 : 2) + '%'}` : ''}`,
      )
    })
    cy.nodes().forEach((node) => {
      const hl = node.data('half_life_human')
      if (hl) node.data('id2', `${node.id()}\n${hl}`)
    })
    cy.on('tap', 'node', (event) => {
      api.decayInfo(event.target.id()).then(setSelectedInfo).catch(() => {})
    })
    return () => cy.destroy()
  }, [chain])

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Starting nuclide">
            <NuclideInput
              value={nuclide}
              nuclides={nuclides}
              onChange={(n) =>
                setParams((prev) => {
                  const next = new URLSearchParams(prev)
                  next.set('nuclide', n)
                  return next
                })
              }
            />
          </Field>
          <Field label="Min branching ratio">
            <Select
              value={minBr}
              onChange={(v) =>
                setParams((prev) => {
                  const next = new URLSearchParams(prev)
                  next.set('minbr', v)
                  return next
                })
              }
              options={[
                { value: '0', label: 'all branches' },
                { value: '0.0001', label: '≥ 0.01%' },
                { value: '0.01', label: '≥ 1%' },
                { value: '0.05', label: '≥ 5%' },
              ]}
            />
          </Field>
          {chain && (
            <p className="pb-2 text-xs text-[var(--text-muted)]">
              {chain.nodes.length} nuclides · {chain.edges.length} branches · {chain.source}
            </p>
          )}
        </div>
      </Panel>

      <ErrorNote error={error} />

      <div className="flex gap-4">
        <Panel className="flex-1">
          <div ref={containerRef} className="h-[620px] w-full" />
          <div className="mt-1 flex flex-wrap gap-3 text-xs text-[var(--text-secondary)]">
            {Object.entries({ 'β⁻': '#3987e5', 'β⁺/EC': '#199e70', α: '#c98500', IT: '#d55181', SF: '#9085e9' }).map(
              ([label, color]) => (
                <span key={label} className="flex items-center gap-1.5">
                  <span className="inline-block h-0.5 w-4" style={{ backgroundColor: color }} />
                  {label}
                </span>
              ),
            )}
            <span className="text-[var(--text-muted)]">
              Edge width ∝ √(branching ratio) · layout follows (N, Z) like the chart of nuclides
            </span>
          </div>
        </Panel>

        <div className="w-80 shrink-0">
          <Panel>
            <h2 className="text-sm font-medium">
              {selectedInfo ? displayNuclide(selectedInfo.nuclide) : 'Nuclide'}
            </h2>
            {selectedInfo ? (
              <div className="mt-1 space-y-1 text-xs text-[var(--text-secondary)]">
                <p>
                  Half-life:{' '}
                  <span className="tabular-nums">
                    {selectedInfo.stable ? 'stable' : selectedInfo.half_life_human ?? 'unknown'}
                  </span>
                </p>
                {selectedInfo.decay_energy_ev != null && (
                  <p>
                    Mean decay energy:{' '}
                    <span className="tabular-nums">
                      {(selectedInfo.decay_energy_ev / 1e6).toFixed(3)} MeV
                    </span>
                  </p>
                )}
                {selectedInfo.modes.length > 0 && (
                  <table className="mt-2 w-full">
                    <thead className="text-[var(--text-muted)]">
                      <tr className="text-left">
                        <th className="py-0.5 font-normal">Mode</th>
                        <th className="py-0.5 font-normal">Daughter</th>
                        <th className="py-0.5 text-right font-normal">BR</th>
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {selectedInfo.modes.map((m) => (
                        <tr key={`${m.mode}-${m.daughter}`} className="border-t border-[var(--border)]">
                          <td className="py-1">{m.mode}</td>
                          <td className="py-1">{m.daughter ? displayNuclide(m.daughter) : '—'}</td>
                          <td className="py-1 text-right">
                            {m.branching_ratio < 0.001
                              ? m.branching_ratio.toExponential(2)
                              : `${(m.branching_ratio * 100).toPrecision(4)}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <p className="pt-1 text-[10px] text-[var(--text-muted)]">{selectedInfo.source}</p>
              </div>
            ) : (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {info ? '' : 'Enter a nuclide to draw its chain.'}
              </p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}
