/**
 * Export controls: CSV (full-resolution data from the backend, with citation
 * headers) and PNG (current plot, 2x publication scale, citations stamped in
 * the footer). Both honor the traceability rule: no export leaves NIDE
 * without the citation of the evaluation(s) it came from.
 */
import { downloadPng } from '../../lib/plotly'

interface Props {
  csvUrl: string | null
  pngFilename: string
  plotElement: HTMLDivElement | null
  citations: string[]
}

const buttonClass =
  'px-2.5 py-1.5 rounded-md text-xs border border-[var(--border)] text-[var(--text-secondary)] ' +
  'hover:text-[var(--text-primary)] hover:border-[var(--accent)] transition-colors'

export default function ExportButtons({ csvUrl, pngFilename, plotElement, citations }: Props) {
  return (
    <div className="flex gap-2">
      {csvUrl && (
        <a className={buttonClass} href={csvUrl} download>
          Export CSV
        </a>
      )}
      <button
        className={buttonClass}
        disabled={!plotElement}
        onClick={() => {
          if (plotElement) void downloadPng(plotElement, pngFilename, citations)
        }}
      >
        Export PNG
      </button>
    </div>
  )
}
