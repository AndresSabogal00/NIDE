/**
 * Interactive chart of nuclides (Segrè chart) with zoom-dependent level of
 * detail, modeled on the IAEA Live Chart of Nuclides: N on x, Z on y, one
 * cell per NUBASE2020 ground state.
 *
 * Rendering: a single canvas redrawn on demand (requestAnimationFrame,
 * viewport-culled). ~3 500 cells redraw in well under a frame; text is only
 * laid out for cells actually visible at a text-bearing zoom level, so the
 * cost of high zoom is bounded by the viewport, not the dataset.
 *
 * Interaction: wheel / trackpad-pinch zoom anchored at the cursor, drag to
 * pan, click to pin a nuclide in the detail panel. Level of detail grows
 * with the on-screen cell size:
 *
 *   < 14 px   color only (the classic far-view chart)
 *   >= 14 px  mass number + element symbol
 *   >= 44 px  + half-life (or "stable")
 *   >= 64 px  + primary decay mode
 *   >= 84 px  + spin/parity
 *
 * Color modes are unchanged from the static version: decay mode
 * (categorical, fixed palette order), half-life / abundance / thermal
 * capture sigma (sequential blue ramp, log scale, dark end = low so
 * near-zero recedes into the dark surface).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ChartNuclide } from '../../api/client'
import { displayNuclide } from '../../lib/format'
import { ErrorNote, Field, Panel, Select } from '../controls'

const PAD = 30 // axis gutter inside the canvas, px
const CANVAS_HEIGHT = 680

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
  ['n', '#d95926', 'n'],
]
const STABLE_COLOR = '#e8e7e0'
const UNKNOWN_COLOR = '#383835'

/** Sequential blue ramp (palette steps 100..700), dark end = low. */
const RAMP = ['#0d366b', '#104281', '#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4', '#cde2fb']

function rampColor(t: number): string {
  return RAMP[Math.floor(Math.min(Math.max(t, 0), 0.999) * RAMP.length)]
}

function modeColor(mode: string | null): string {
  if (!mode) return UNKNOWN_COLOR
  // NUBASE writes multi-particle modes with a leading count ('2B-', '2p');
  // strip it so they inherit the base mode's color.
  const base = mode.replace(/^\d+/, '')
  const hit = MODE_COLORS.find(([key]) => base === key || base.startsWith(key))
  return hit ? hit[1] : UNKNOWN_COLOR
}

/** Dark text on light cells, light text on dark cells (quick luma test). */
function textColorFor(hex: string): string {
  const v = parseInt(hex.slice(1), 16)
  const luma = 0.299 * ((v >> 16) & 255) + 0.587 * ((v >> 8) & 255) + 0.114 * (v & 255)
  return luma > 150 ? '#0d0d0d' : '#ffffff'
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

/** Human label for a NUBASE decay-mode token ('B-' -> 'β⁻'). */
function modeLabel(mode: string | null): string {
  if (!mode) return '?'
  return mode.replace('B-', 'β⁻').replace('B+', 'β⁺').replace('A', 'α').replace('SF', 'SF')
}

interface View {
  scale: number // px per cell
  x0: number // world N at the left edge of the plot area
  y0: number // world Z at the bottom edge of the plot area
}

export default function NuclideChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const view = useRef<View>({ scale: 7, x0: -1, y0: -1 })
  const drag = useRef<{ px: number; py: number; moved: number } | null>(null)
  const rafPending = useRef(false)

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
      if (colorMode === 'decay') return nc.stable ? STABLE_COLOR : modeColor(nc.primary_decay_mode)
      if (colorMode === 'halflife') {
        if (nc.stable) return STABLE_COLOR
        if (nc.half_life_s == null) return UNKNOWN_COLOR
        // 1 ns .. 10 Gyr spans ~26 decades; normalize log10 over it.
        return rampColor((Math.log10(nc.half_life_s) + 9) / 26)
      }
      if (colorMode === 'abundance') {
        if (nc.abundance_pct == null) return UNKNOWN_COLOR
        return rampColor(Math.log10(Math.max(nc.abundance_pct, 1e-4)) / 4 + 0.5)
      }
      const sigma = capture?.[nc.nuclide]
      if (sigma == null) return UNKNOWN_COLOR
      // 1 mb .. 100 kb: log10 in [-3, 5] -> [0, 1]
      return rampColor((Math.log10(sigma) + 3) / 8)
    },
    [colorMode, capture],
  )

  const fitView = useCallback((): View => {
    const canvas = canvasRef.current
    if (!canvas) return { scale: 7, x0: -1, y0: -1 }
    const w = canvas.clientWidth - PAD
    const h = canvas.clientHeight - PAD
    const scale = Math.min(w / (maxN + 4), h / (maxZ + 4))
    return { scale, x0: -2, y0: -2 }
  }, [maxN, maxZ])

  // ------------------------------------------------------------------ //
  // Drawing                                                             //
  // ------------------------------------------------------------------ //

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || !nuclides.length) return
    const dpr = window.devicePixelRatio || 1
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr
      canvas.height = h * dpr
    }
    const ctx = canvas.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    const { scale, x0, y0 } = view.current
    const sx = (n: number) => PAD + (n - x0) * scale
    const sy = (z: number) => h - PAD - (z - y0 + 1) * scale // top edge of cell z

    // Visible world window (with one-cell margin).
    const nMin = Math.max(0, Math.floor(x0) - 1)
    const nMax = Math.min(maxN, Math.ceil(x0 + (w - PAD) / scale) + 1)
    const zMin = Math.max(0, Math.floor(y0) - 1)
    const zMax = Math.min(maxZ, Math.ceil(y0 + (h - PAD) / scale) + 1)

    const gap = scale > 5 ? Math.max(1, scale * 0.06) : scale > 2.5 ? 0.5 : 0
    const cell = scale - gap

    // Iterate the sparse grid: when zoomed out the nuclide array is the
    // cheaper loop; when zoomed in, the visible (n, z) window is tiny.
    const visibleCount = (nMax - nMin + 1) * (zMax - zMin + 1)
    const cells: ChartNuclide[] = []
    if (visibleCount < nuclides.length) {
      for (let z = zMin; z <= zMax; z++)
        for (let n = nMin; n <= nMax; n++) {
          const nc = byCell.get(z * 512 + n)
          if (nc) cells.push(nc)
        }
    } else {
      for (const nc of nuclides) if (nc.n >= nMin && nc.n <= nMax && nc.z >= zMin && nc.z <= zMax) cells.push(nc)
    }

    for (const nc of cells) {
      const color = cellColor(nc)
      ctx.fillStyle = color
      const x = sx(nc.n)
      const y = sy(nc.z)
      ctx.fillRect(x, y, cell, cell)

      // Level-of-detail text, one threshold at a time (IAEA Live Chart UX).
      if (scale >= 14) {
        const ink = textColorFor(color)
        ctx.fillStyle = ink
        ctx.textAlign = 'center'
        const cx = x + cell / 2
        if (scale < 44) {
          ctx.font = `${Math.max(5, scale * 0.34)}px system-ui`
          ctx.textBaseline = 'middle'
          ctx.fillText(`${nc.a}${nc.symbol}`, cx, y + cell / 2, cell - 2)
        } else {
          const lines: [string, number][] = [
            [`${nc.a}${nc.symbol}`, 0.24],
            [nc.stable ? 'stable' : humanHalfLife(nc.half_life_s), 0.15],
          ]
          if (scale >= 64) lines.push([nc.stable ? `${nc.abundance_pct ?? '—'}%` : modeLabel(nc.primary_decay_mode), 0.14])
          if (scale >= 84 && nc.spin_parity) lines.push([nc.spin_parity, 0.12])
          ctx.textBaseline = 'alphabetic'
          let ty = y + cell * 0.3
          for (const [text, size] of lines) {
            ctx.font = `${text === lines[0][0] ? '600 ' : ''}${scale * size}px system-ui`
            ctx.fillText(text, cx, ty, cell - 4)
            ty += cell * (size + 0.06)
          }
        }
      }
    }

    // Magic numbers (shell closures), the standard chart annotation.
    ctx.strokeStyle = 'rgba(195,194,183,0.35)'
    ctx.setLineDash([3, 3])
    ctx.fillStyle = '#898781'
    ctx.font = '10px system-ui'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
    for (const magic of [2, 8, 20, 28, 50, 82, 126]) {
      if (magic <= maxN + 1) {
        const x = sx(magic)
        if (x > PAD && x < w) {
          ctx.beginPath()
          ctx.moveTo(x, h - PAD)
          ctx.lineTo(x, 0)
          ctx.stroke()
          ctx.fillText(String(magic), x + 2, h - PAD + 12)
        }
      }
      if (magic <= maxZ + 1) {
        const y = sy(magic) + scale
        if (y > 0 && y < h - PAD) {
          ctx.beginPath()
          ctx.moveTo(PAD, y)
          ctx.lineTo(w, y)
          ctx.stroke()
          ctx.fillText(String(magic), 2, y - 2)
        }
      }
    }
    ctx.setLineDash([])
    ctx.fillText('N →', w - 34, h - 8)
    ctx.save()
    ctx.translate(10, 40)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText('Z →', -30, 0)
    ctx.restore()

    // Hover and selection outlines.
    for (const [nc, style, width] of [
      [hover, 'rgba(255,255,255,0.8)', 1] as const,
      [selected, '#ffffff', 2] as const,
    ]) {
      if (!nc) continue
      ctx.strokeStyle = style
      ctx.lineWidth = width
      ctx.strokeRect(sx(nc.n) - 1, sy(nc.z) - 1, cell + 2, cell + 2)
    }
  }, [nuclides, byCell, cellColor, hover, selected, maxN, maxZ])

  const scheduleDraw = useCallback(() => {
    if (rafPending.current) return
    rafPending.current = true
    requestAnimationFrame(() => {
      rafPending.current = false
      draw()
    })
  }, [draw])

  // Redraw when data / mode / hover / selection change, and on resize.
  useEffect(() => {
    scheduleDraw()
  }, [scheduleDraw])
  useEffect(() => {
    if (nuclides.length) {
      view.current = fitView()
      scheduleDraw()
    }
  }, [nuclides.length, fitView, scheduleDraw])
  useEffect(() => {
    const observer = new ResizeObserver(scheduleDraw)
    if (wrapRef.current) observer.observe(wrapRef.current)
    return () => observer.disconnect()
  }, [scheduleDraw])

  // ------------------------------------------------------------------ //
  // Interaction: wheel zoom (cursor-anchored), drag pan, hover, click   //
  // ------------------------------------------------------------------ //

  const locate = useCallback(
    (clientX: number, clientY: number): ChartNuclide | null => {
      const canvas = canvasRef.current
      if (!canvas) return null
      const rect = canvas.getBoundingClientRect()
      const { scale, x0, y0 } = view.current
      const n = Math.floor(x0 + (clientX - rect.left - PAD) / scale)
      const z = Math.floor(y0 + (canvas.clientHeight - PAD - (clientY - rect.top)) / scale)
      return byCell.get(z * 512 + n) ?? null
    },
    [byCell],
  )

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    // Native non-passive listener: wheel must preventDefault or the page
    // scrolls/zooms instead of the chart (trackpad pinch arrives as
    // ctrl+wheel on macOS and is covered by the same handler).
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const { scale, x0, y0 } = view.current
      const factor = Math.exp(-event.deltaY * (event.ctrlKey ? 0.008 : 0.0015))
      const fit = fitView().scale
      const next = Math.min(Math.max(scale * factor, fit * 0.85), 150)
      // Keep the world point under the cursor fixed while zooming.
      const px = event.clientX - rect.left - PAD
      const py = canvas.clientHeight - PAD - (event.clientY - rect.top)
      view.current = {
        scale: next,
        x0: x0 + px / scale - px / next,
        y0: y0 + py / scale - py / next,
      }
      scheduleDraw()
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [fitView, scheduleDraw])

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
          <button
            className="ml-auto rounded-md border border-[var(--border)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--text-primary)]"
            onClick={() => {
              view.current = fitView()
              scheduleDraw()
            }}
          >
            Reset view
          </button>
        </div>
      </Panel>

      <ErrorNote error={error} />

      <div className="flex gap-4">
        <Panel className="min-w-0 flex-1">
          <div ref={wrapRef}>
            <canvas
              ref={canvasRef}
              className="w-full cursor-crosshair touch-none select-none"
              style={{ height: CANVAS_HEIGHT }}
              onPointerDown={(e) => {
                drag.current = { px: e.clientX, py: e.clientY, moved: 0 }
                e.currentTarget.setPointerCapture(e.pointerId)
              }}
              onPointerMove={(e) => {
                if (drag.current) {
                  const dx = e.clientX - drag.current.px
                  const dy = e.clientY - drag.current.py
                  drag.current.px = e.clientX
                  drag.current.py = e.clientY
                  drag.current.moved += Math.abs(dx) + Math.abs(dy)
                  const { scale, x0, y0 } = view.current
                  view.current = { scale, x0: x0 - dx / scale, y0: y0 + dy / scale }
                  scheduleDraw()
                } else {
                  setHover(locate(e.clientX, e.clientY))
                }
              }}
              onPointerUp={(e) => {
                const wasClick = (drag.current?.moved ?? 0) < 4
                drag.current = null
                if (wasClick) setSelected(locate(e.clientX, e.clientY))
              }}
              onPointerLeave={() => {
                drag.current = null
                setHover(null)
              }}
            />
          </div>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            Scroll / pinch to zoom (labels appear as cells grow), drag to pan, click to pin a
            nuclide. Dashed lines: magic numbers. {citation}
          </p>
        </Panel>

        <div className="w-80 shrink-0 space-y-4">
          <Panel>
            <h2 className="text-sm font-medium">Hover</h2>
            {hover ? (
              <NuclideSummary nuclide={hover} capture={capture} />
            ) : (
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
                    <Link
                      className="text-[var(--accent)] hover:underline"
                      to={`/compare?nuclide=${selected.nuclide}&mt=102`}
                    >
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
