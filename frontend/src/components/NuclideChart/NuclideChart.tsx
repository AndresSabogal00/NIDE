/**
 * Interactive chart of nuclides (Segrè chart): N on x, Z on y, one cell per
 * ground state from NUBASE2020. Canvas-rendered (≈3500 cells redraw in <5 ms,
 * far beyond SVG comfort), with pointer hit-testing for hover/click.
 *
 * Color modes:
 *  - decay mode  — categorical, palette hues in fixed order per mode
 *  - half-life   — sequential (log10 scale over 24 decades)
 *  - abundance   — sequential, stable nuclides only
 *  - sigma(n,g)  — sequential (log10), thermal capture from the selected
 *                  library (computed server-side, cached)
 * Stable nuclides are drawn near-white in every mode, the printed-chart
 * convention adapted to a dark surface.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ChartNuclide } from '../../api/client'
import { displayNuclide } from '../../lib/format'
import { ErrorNote, Field, Panel, Select } from '../controls'

const CELL = 7 // px per nuclide cell at devicePixelRatio 1
const PAD = 34 // axis label gutter, px

type ColorMode = 'decay' | 'halflife' | 'abundance' | 'capture'

/** Categorical colors per decay mode (dark palette slots, fixed order). */
const MODE_COLORS: [string, string, string][] = [
  ['B-', '#3987e5', 'β⁻'],
  ['B+', '#199e70', 'β⁺/EC'],
  ['EC', '#199e70', ''],
  ['A', '#c98500', 'α'],
  ['SF', '#9085e9', 'SF'],
  ['IT', '#d55181', 'IT'],
  ['p', '#e66767', 'p'],
  ['2p', '#e66767', ''],
  ['n', '#d95926', 'n'],
  ['2n', '#d95926', ''],
]
const STABLE_COLOR = '#e8e7e0'
const UNKNOWN_COLOR = '#383835'

/** Sequential blue ramp (palette steps 100..700); on the dark surface the
 * dark end encodes "low" so near-zero recedes toward the background. */
const RAMP = ['#0d366b', '#104281', '#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4', '#cde2fb']

function rampColor(t: number): string {
  const clamped = Math.min(Math.max(t, 0), 0.999)
  return RAMP[Math.floor(clamped * RAMP.length)]
}

function modeColor(mode: string | null): string {
  if (!mode) return UNKNOWN_COLOR
  const hit = MODE_COLORS.find(([key]) => mode === key || mode.startsWith(key))
  return hit ? hit[1] : UNKNOWN_COLOR
}

export default function NuclideChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [nuclides, setNuclides] = useState<ChartNuclide[]>([])
  const [citation, setCitation] = useState('')
  const [colorMode, setColorMode] = useState<ColorMode>('decay')
  const [capture, setCapture] = useState<Record<string, number> | null>(null)
  const [captureLoading, setCaptureLoading] = useState(false)
  const [hover, setHover] = useState<ChartNuclide | null>(null)
  const [selected, setSelected] = useState<ChartNuclide | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .chartNuclides('endfb80')
      .then((d) => {
        setNuclides(d.nuclides)
        setCitation(d.citation)
      })
      .catch((e) => setError(String(e.message)))
  }, [])

  // Thermal-capture map is fetched only when that mode is first selected:
  // the first request per library computes ~500 HDF5 loads server-side.
  useEffect(() => {
    if (colorMode !== 'capture' || capture || captureLoading) return
    setCaptureLoading(true)
    api
      .thermalCaptureMap('endfb80')
      .then((d) => setCapture(d.sigma_thermal_capture_barns))
      .catch((e) => setError(`Thermal capture map: ${e.message}`))
      .finally(() => setCaptureLoading(false))
  }, [colorMode, capture, captureLoading])

  const { maxN, maxZ, byCell } = useMemo(() => {
    let n = 0
    let z = 0
    const index = new Map<number, ChartNuclide>()
    for (const nc of nuclides) {
      n = Math.max(n, nc.n)
      z = Math.max(z, nc.z)
      index.set(nc.z * 512 + nc.n, nc)
    }
    return { maxN: n, maxZ: z, byCell: index }
  }, [nuclides])

  const cellColor = useCallback(
    (nc: ChartNuclide): string => {
      if (colorMode === 'decay') {
        return nc.stable ? STABLE_COLOR : modeColor(nc.primary_decay_mode)
      }
      if (colorMode === 'halflife') {
        if (nc.stable) return STABLE_COLOR
        if (nc.half_life_s == null) return UNKNOWN_COLOR
        // 1 ns .. 10 Gyr spans ~26 decades; normalize log10 over it.
        const t = (Math.log10(nc.half_life_s) + 9) / 26
        return rampColor(t)
      }
      if (colorMode === 'abundance') {
        if (nc.abundance_pct == null) return UNKNOWN_COLOR
        return rampColor(Math.log10(Math.max(nc.abundance_pct, 1e-4)) / 2 / 2 + 0.5)
      }
      // capture
      const sigma = capture?.[nc.nuclide]
      if (sigma == null) return UNKNOWN_COLOR
      // 1 mb .. 100 kb: log10 in [-3, 5] -> [0, 1]
      return rampColor((Math.log10(sigma) + 3) / 8)
    },
    [colorMode, capture],
  )

  // Redraw on any input change.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !nuclides.length) return
    const width = PAD + (maxN + 2) * CELL
    const height = PAD + (maxZ + 2) * CELL
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)

    for (const nc of nuclides) {
      ctx.fillStyle = cellColor(nc)
      // y grows upward in the chart: Z=0 at the bottom.
      ctx.fillRect(PAD + nc.n * CELL, height - PAD - (nc.z + 1) * CELL, CELL - 1, CELL - 1)
    }
    // Magic numbers, the standard chart annotation (shell closures).
    ctx.strokeStyle = 'rgba(195,194,183,0.35)'
    ctx.setLineDash([3, 3])
    for (const magic of [2, 8, 20, 28, 50, 82, 126]) {
      if (magic <= maxN + 1) {
        ctx.beginPath()
        ctx.moveTo(PAD + magic * CELL, height - PAD)
        ctx.lineTo(PAD + magic * CELL, 0)
        ctx.stroke()
      }
      if (magic <= maxZ + 1) {
        ctx.beginPath()
        ctx.moveTo(PAD, height - PAD - magic * CELL)
        ctx.lineTo(width, height - PAD - magic * CELL)
        ctx.stroke()
      }
    }
    ctx.setLineDash([])
    ctx.fillStyle = '#898781'
    ctx.font = '11px system-ui'
    ctx.fillText('N →', PAD + 4, height - 10)
    ctx.save()
    ctx.translate(12, height - PAD - 6)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText('Z →', 0, 0)
    ctx.restore()

    if (selected) {
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5
      ctx.strokeRect(
        PAD + selected.n * CELL - 1,
        height - PAD - (selected.z + 1) * CELL - 1,
        CELL + 1,
        CELL + 1,
      )
    }
  }, [nuclides, cellColor, maxN, maxZ, selected])

  const locate = (event: React.MouseEvent<HTMLCanvasElement>): ChartNuclide | null => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    const height = PAD + (maxZ + 2) * CELL
    const n = Math.floor((x - PAD) / CELL)
    const z = Math.floor((height - PAD - y) / CELL)
    return byCell.get(z * 512 + n) ?? null
  }

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Color by">
            <Select
              value={colorMode}
              onChange={(v) => setColorMode(v as ColorMode)}
              options={[
                { value: 'decay', label: 'Decay mode' },
                { value: 'halflife', label: 'Half-life' },
                { value: 'abundance', label: 'Isotopic abundance' },
                { value: 'capture', label: 'Thermal capture σ (ENDF/B-VIII.0)' },
              ]}
            />
          </Field>
          {colorMode === 'decay' ? (
            <div className="flex flex-wrap items-center gap-3 pb-1 text-xs text-[var(--text-secondary)]">
              <LegendChip color={STABLE_COLOR} label="stable" />
              {MODE_COLORS.filter(([, , label]) => label).map(([key, color, label]) => (
                <LegendChip key={key} color={color} label={label} />
              ))}
              <LegendChip color={UNKNOWN_COLOR} label="unknown" />
            </div>
          ) : (
            <div className="flex items-center gap-2 pb-1 text-xs text-[var(--text-muted)]">
              <span>low</span>
              <div
                className="h-2.5 w-40 rounded-sm"
                style={{ background: `linear-gradient(to right, ${RAMP.join(',')})` }}
              />
              <span>high (log scale)</span>
              {colorMode === 'capture' && captureLoading && (
                <span className="ml-2">computing map from ENDF/B-VIII.0 (first time only)…</span>
              )}
            </div>
          )}
        </div>
      </Panel>

      <ErrorNote error={error} />

      <div className="flex gap-4">
        <Panel className="overflow-auto">
          <canvas
            ref={canvasRef}
            className="cursor-crosshair"
            onMouseMove={(e) => setHover(locate(e))}
            onMouseLeave={() => setHover(null)}
            onClick={(e) => setSelected(locate(e))}
          />
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            Dashed lines: magic numbers (2, 8, 20, 28, 50, 82, 126). {citation}
          </p>
        </Panel>

        <div className="w-80 shrink-0 space-y-4">
          <Panel>
            <h2 className="text-sm font-medium">Hover</h2>
            {hover ? <NuclideSummary nuclide={hover} capture={capture} /> : (
              <p className="mt-1 text-xs text-[var(--text-muted)]">Move over the chart…</p>
            )}
          </Panel>
          <Panel>
            <h2 className="text-sm font-medium">Selected</h2>
            {selected ? (
              <>
                <NuclideSummary nuclide={selected} capture={capture} />
                <div className="mt-3 flex flex-col gap-1.5 text-sm">
                  {selected.has_xs_data && (
                    <Link className="text-[var(--accent)] hover:underline" to={`/xs?nuclide=${selected.nuclide}`}>
                      → Cross sections
                    </Link>
                  )}
                  {selected.has_xs_data && (
                    <Link className="text-[var(--accent)] hover:underline" to={`/compare?nuclide=${selected.nuclide}&mt=102`}>
                      → Compare libraries
                    </Link>
                  )}
                  {!selected.stable && (
                    <Link className="text-[var(--accent)] hover:underline" to={`/decay?nuclide=${selected.nuclide}`}>
                      → Decay chain
                    </Link>
                  )}
                </div>
              </>
            ) : (
              <p className="mt-1 text-xs text-[var(--text-muted)]">Click a nuclide.</p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}

function LegendChip({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

function NuclideSummary({
  nuclide: nc,
  capture,
}: {
  nuclide: ChartNuclide
  capture: Record<string, number> | null
}) {
  const rows: [string, string][] = [
    ['Z / N / A', `${nc.z} / ${nc.n} / ${nc.a}`],
    ['Half-life', nc.stable ? 'stable' : humanHalfLife(nc.half_life_s)],
    ['Decay mode', nc.primary_decay_mode ?? (nc.stable ? '—' : 'unknown')],
    ['Abundance', nc.abundance_pct != null ? `${nc.abundance_pct}%` : '—'],
    ['Spin/parity', nc.spin_parity ?? '—'],
    ['Mass excess', nc.mass_excess_kev != null ? `${nc.mass_excess_kev.toFixed(1)} keV` : '—'],
  ]
  const sigma = capture?.[nc.nuclide]
  if (sigma != null) rows.push(['σ(n,γ) thermal', `${Number(sigma.toPrecision(3))} b`])
  return (
    <div className="mt-1">
      <p className="text-base font-semibold">{displayNuclide(nc.nuclide)}</p>
      <table className="mt-1 w-full text-xs text-[var(--text-secondary)]">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td className="py-0.5 pr-2 text-[var(--text-muted)]">{k}</td>
              <td className="py-0.5 tabular-nums">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {nc.half_life_from_systematics && (
        <p className="mt-1 text-[10px] text-[var(--text-muted)]">half-life from systematics (#)</p>
      )}
    </div>
  )
}

function humanHalfLife(seconds: number | null): string {
  if (seconds == null) return 'unknown'
  const units: [number, string][] = [
    [3.15576e16, 'Gyr'],
    [3.15576e13, 'Myr'],
    [3.15576e7, 'yr'],
    [86400, 'd'],
    [3600, 'h'],
    [60, 'min'],
    [1, 's'],
    [1e-3, 'ms'],
    [1e-6, 'µs'],
    [1e-9, 'ns'],
  ]
  for (const [factor, unit] of units) {
    if (seconds >= factor) return `${Number((seconds / factor).toPrecision(3))} ${unit}`
  }
  return `${seconds.toExponential(2)} s`
}
