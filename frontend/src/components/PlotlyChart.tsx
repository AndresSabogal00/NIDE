/**
 * Thin React wrapper around plotly.js: imperative Plotly.react on prop
 * change, cleanup on unmount, and a ref escape hatch for image export.
 */
import { useEffect, useRef } from 'react'
import { Plotly } from '../lib/plotly'

interface Props {
  data: Plotly.Data[]
  layout: Partial<Plotly.Layout>
  className?: string
  onReady?: (element: HTMLDivElement) => void
}

export default function PlotlyChart({ data, layout, className, onReady }: Props) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    void Plotly.react(container.current, data, layout as Plotly.Layout, {
      responsive: true,
      displaylogo: false,
      // PNG export is handled by the ExportButtons component (it stamps
      // citations); keep the modebar minimal and scientific.
      modeBarButtonsToRemove: ['lasso2d', 'select2d', 'toImage'],
    }).then(() => {
      if (container.current && onReady) onReady(container.current)
    })
  }, [data, layout, onReady])

  useEffect(() => {
    const element = container.current
    return () => {
      if (element) Plotly.purge(element)
    }
  }, [])

  return <div ref={container} className={className} />
}
