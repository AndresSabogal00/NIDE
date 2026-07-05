/**
 * Shared selection context: the nuclide / reaction / library / temperature
 * the user is working with, plus cross-view toggles (EXFOR overlay,
 * discrepancy threshold).
 *
 * Why this exists: each view keeps its parameters in the URL search string
 * (good for deep links), but navigating through the top bar goes to bare
 * paths — without shared state the views would fall back to hardcoded
 * defaults and the user's selection would silently reset (the "Th-227
 * becomes U-235 again" bug). Resolution order everywhere is:
 *
 *   URL param (deep link / back button)  >  this context  >  default
 *
 * The context is kept in sessionStorage so a reload within the same browser
 * session also preserves the selection; a fresh session starts clean at the
 * documented defaults.
 */
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

export interface Selection {
  nuclide: string
  mt: number
  libraries: string[]
  temperature: string
  exfor: boolean
  thresholdPercent: number
  referenceLibrary: string
}

const DEFAULTS: Selection = {
  nuclide: 'U235',
  mt: 18,
  libraries: ['endfb80'],
  temperature: '294K',
  exfor: false,
  thresholdPercent: 5,
  referenceLibrary: 'endfb80',
}

const STORAGE_KEY = 'nide-selection'

function load(): Selection {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    /* corrupted storage: fall through to defaults */
  }
  return DEFAULTS
}

interface ContextValue {
  selection: Selection
  update: (partial: Partial<Selection>) => void
}

const SelectionContext = createContext<ContextValue>({ selection: DEFAULTS, update: () => {} })

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<Selection>(load)
  const update = useCallback((partial: Partial<Selection>) => {
    setSelection((previous) => {
      const next = { ...previous, ...partial }
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        /* storage may be unavailable (private mode); in-memory still works */
      }
      return next
    })
  }, [])
  return <SelectionContext.Provider value={{ selection, update }}>{children}</SelectionContext.Provider>
}

export function useSelection(): ContextValue {
  return useContext(SelectionContext)
}
