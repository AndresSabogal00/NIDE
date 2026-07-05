import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Nuclide Chart' },
  { to: '/xs', label: 'Cross Sections' },
  { to: '/compare', label: 'Compare' },
  { to: '/decay', label: 'Decay Chains' },
  { to: '/yields', label: 'Fission Yields' },
]

export default function Layout() {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-[var(--border)] bg-[var(--surface-1)]">
        <div className="mx-auto max-w-screen-2xl px-6 py-3 flex items-baseline gap-8">
          <h1 className="text-lg font-semibold tracking-tight">
            NIDE
            <span className="ml-3 text-xs font-normal text-[var(--text-muted)]">
              Nuclear Information &amp; Data Explorer
            </span>
          </h1>
          <nav className="flex gap-1 text-sm">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition-colors ${
                    isActive
                      ? 'bg-[var(--accent)]/15 text-[var(--accent)]'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-screen-2xl px-6 py-5">
        <Outlet />
      </main>
      <footer className="border-t border-[var(--border)] px-6 py-3 text-xs text-[var(--text-muted)]">
        Evaluated data: ENDF/B-VIII.0 · JEFF-3.3 · JENDL-5 (HDF5 processing by the OpenMC project) ·
        Experimental data: EXFOR (IAEA-NDS) · Structure data: NUBASE2020 · Every value is traceable
        to its evaluation — citations shown per view.
      </footer>
    </div>
  )
}
