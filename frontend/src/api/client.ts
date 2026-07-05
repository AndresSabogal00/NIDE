/**
 * Typed client for the NIDE backend REST API.
 *
 * Conventions mirror the backend: energies in eV, cross sections in barns,
 * nuclide names in GNDS style ("U235", "Am242_m1"), reactions as ENDF MT
 * numbers. Every response that carries physics data also carries the
 * citation of its source evaluation — surfaced verbatim in the UI.
 */

export interface LibraryInfo {
  library_id: string
  name: string
  version: string
  citation: string
  doi: string
  n_nuclides: number
}

export interface ReactionEntry {
  mt: number
  name: string
  redundant: boolean
}

export interface NuclideReactions {
  library_id: string
  nuclide: string
  temperatures: string[]
  reactions: ReactionEntry[]
}

export interface XSCurve {
  library_id: string
  library_name: string
  nuclide: string
  mt: number
  reaction_name: string
  temperature: string
  energy_ev: number[]
  xs_barns: number[]
  n_points_full: number
  downsampled: boolean
  citation: string
}

export interface RegionStats {
  library_id: string
  region: 'thermal' | 'epithermal' | 'fast'
  e_min_ev: number
  e_max_ev: number
  n_points: number
  max_abs_diff_percent: number
  mean_abs_diff_percent: number
  median_abs_diff_percent: number
  energy_at_max_ev: number
}

export interface Comparison {
  nuclide: string
  mt: number
  reaction_name: string
  reference_library: string
  threshold_percent: number
  missing_libraries: string[]
  energy_ev: number[]
  curves: Record<string, (number | null)[]>
  diff_percent: Record<string, (number | null)[]>
  region_stats: RegionStats[]
  discrepancies: {
    library_id: string
    e_min_ev: number
    e_max_ev: number
    max_abs_diff_percent: number
  }[]
  summary: string[]
  citations: Record<string, string>
}

export interface DerivedQuantities {
  nuclide: string
  mt: number
  reaction_name: string
  temperature: string
  results: {
    library_id: string
    library_name: string
    thermal_xs_barns: number | null
    resonance_integral_barns: number | null
    maxwellian_avg_barns: number | null
    maxwellian_temperature_k: number
    watt_avg_barns: number | null
    westcott_g_factor: number | null
  }[]
  definitions: Record<string, string>
}

export interface DecayMode {
  mode: string
  daughter: string | null
  branching_ratio: number
  branching_ratio_uncertainty: number
}

export interface DecayInfo {
  nuclide: string
  z: number
  a: number
  isomeric_state: number
  stable: boolean
  half_life_s: number | null
  half_life_uncertainty_s: number | null
  half_life_human: string | null
  decay_energy_ev: number | null
  modes: DecayMode[]
  source: string
}

export interface DecayChain {
  start: string
  nodes: { data: Record<string, unknown> }[]
  edges: { data: Record<string, unknown> }[]
  source: string
}

export interface YieldSet {
  energy_ev: number
  energy_label: string
  by_mass_number: Record<string, number>
  by_atomic_number: Record<string, number>
  top_products: [string, number][]
}

export interface FissionYields {
  nuclide: string
  yield_type: 'independent' | 'cumulative'
  sets: YieldSet[]
  source: string
}

export interface ChartNuclide {
  nuclide: string
  z: number
  n: number
  a: number
  symbol: string
  stable: boolean
  half_life_s: number | null
  half_life_from_systematics: boolean
  primary_decay_mode: string | null
  abundance_pct: number | null
  mass_excess_kev: number | null
  spin_parity: string | null
  has_xs_data: boolean
}

export interface ExforDataset {
  entry: string
  author: string
  year: number | null
  reference: string
  points: { energy_ev: number; xs_barns: number; denergy_ev: number | null; dxs_barns: number | null }[]
}

export interface ExforResponse {
  nuclide: string
  mt: number
  available: boolean
  message: string | null
  datasets: ExforDataset[]
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `${response.status} ${response.statusText}`)
  }
  return response.json()
}

export const api = {
  libraries: () => get<LibraryInfo[]>('/api/libraries'),
  nuclides: (library: string) => get<string[]>(`/api/libraries/${library}/nuclides`),
  reactions: (nuclide: string, library: string) =>
    get<NuclideReactions>(`/api/nuclides/${nuclide}/reactions?library=${library}`),
  xs: (nuclide: string, mt: number, library: string, temperature: string, maxPoints = 5000) =>
    get<XSCurve>(
      `/api/xs?nuclide=${nuclide}&mt=${mt}&library=${library}&temperature=${temperature}&max_points=${maxPoints}`,
    ),
  compare: (nuclide: string, mt: number, libraries: string[], threshold: number, temperature: string) =>
    get<Comparison>(
      `/api/compare?nuclide=${nuclide}&mt=${mt}&libraries=${libraries.join(',')}&threshold=${threshold}&temperature=${temperature}`,
    ),
  derived: (nuclide: string, mt: number, libraries: string[], temperature: string) =>
    get<DerivedQuantities>(
      `/api/derived?nuclide=${nuclide}&mt=${mt}&libraries=${libraries.join(',')}&temperature=${temperature}`,
    ),
  decayInfo: (nuclide: string) => get<DecayInfo>(`/api/decay/${nuclide}`),
  decayChain: (nuclide: string, minBr: number) =>
    get<DecayChain>(`/api/decay/${nuclide}/chain?min_br=${minBr}`),
  fissionYieldNuclides: () => get<string[]>('/api/fission-yields/nuclides'),
  fissionYields: (nuclide: string, yieldType: string) =>
    get<FissionYields>(`/api/fission-yields/${nuclide}?yield_type=${yieldType}`),
  chartNuclides: (library: string) =>
    get<{ citation: string; nuclides: ChartNuclide[] }>(`/api/chart/nuclides?library=${library}`),
  thermalCaptureMap: (library: string) =>
    get<{ library: string; citation: string; sigma_thermal_capture_barns: Record<string, number> }>(
      `/api/chart/thermal-capture?library=${library}`,
    ),
  exfor: (nuclide: string, mt: number) => get<ExforResponse>(`/api/exfor?nuclide=${nuclide}&mt=${mt}`),
}

/** Fixed series colors per library (validated palette; see index.css). */
export const LIBRARY_COLORS: Record<string, string> = {
  endfb80: '#3987e5',
  jeff33: '#199e70',
  jendl5: '#c98500',
}

export const EXFOR_COLOR = '#c3c2b7'

/** Marker symbols cycled per EXFOR dataset: identity via shape, not color. */
export const EXFOR_SYMBOLS = [
  'circle-open',
  'square-open',
  'diamond-open',
  'triangle-up-open',
  'cross-thin-open',
  'x-thin-open',
  'star-open',
] as const
