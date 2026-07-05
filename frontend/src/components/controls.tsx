/** Small shared form controls with the NIDE dark styling. */
import type { ReactNode } from 'react'
import { displayNuclide } from '../lib/format'

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-[var(--text-muted)]">
      {label}
      {children}
    </label>
  )
}

const inputClass =
  'bg-[var(--surface-0)] border border-[var(--border)] rounded-md px-2.5 py-1.5 text-sm ' +
  'text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] min-w-32'

export function NuclideInput({
  value,
  nuclides,
  onChange,
}: {
  value: string
  nuclides: string[]
  onChange: (nuclide: string) => void
}) {
  return (
    <>
      <input
        className={inputClass}
        list="nide-nuclides"
        value={value}
        onChange={(e) => onChange(e.target.value.trim())}
        placeholder="e.g. U235"
        spellCheck={false}
      />
      <datalist id="nide-nuclides">
        {nuclides.map((n) => (
          <option key={n} value={n}>
            {displayNuclide(n)}
          </option>
        ))}
      </datalist>
    </>
  )
}

export function Select({
  value,
  options,
  onChange,
}: {
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  return (
    <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

/** Multi-select of libraries rendered as toggle chips in fixed palette order. */
export function LibraryToggles({
  available,
  selected,
  colors,
  onChange,
}: {
  available: { library_id: string; name: string }[]
  selected: string[]
  colors: Record<string, string>
  onChange: (libs: string[]) => void
}) {
  const toggle = (id: string) => {
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  }
  return (
    <div className="flex gap-2">
      {available.map(({ library_id, name }) => {
        const active = selected.includes(library_id)
        return (
          <button
            key={library_id}
            onClick={() => toggle(library_id)}
            className={`px-2.5 py-1.5 rounded-md text-sm border transition-colors ${
              active
                ? 'border-transparent text-[var(--surface-0)] font-medium'
                : 'border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
            }`}
            style={active ? { backgroundColor: colors[library_id] ?? '#3987e5' } : undefined}
          >
            {name}
          </button>
        )
      })}
    </div>
  )
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <div className="rounded-md border border-[#e66767]/40 bg-[#e66767]/10 px-3 py-2 text-sm text-[#e66767]">
      {error}
    </div>
  )
}

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-4 ${className}`}
    >
      {children}
    </section>
  )
}

export function Citations({ citations }: { citations: string[] }) {
  if (!citations.length) return null
  return (
    <div className="mt-2 space-y-0.5 text-[11px] leading-snug text-[var(--text-muted)]">
      {citations.map((c) => (
        <p key={c}>{c}</p>
      ))}
    </div>
  )
}
