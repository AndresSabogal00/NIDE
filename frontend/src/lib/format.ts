/** Number formatting helpers shared across views (SI-style, physics units). */

/** 0.0253 -> "25.3 meV", 6.67 -> "6.67 eV", 2.1e6 -> "2.1 MeV". */
export function formatEnergy(ev: number): string {
  const abs = Math.abs(ev)
  if (abs >= 1e6) return `${trim(ev / 1e6)} MeV`
  if (abs >= 1e3) return `${trim(ev / 1e3)} keV`
  if (abs >= 1) return `${trim(ev)} eV`
  return `${trim(ev * 1e3)} meV`
}

/** Cross sections: 3 significant figures, scientific below 1e-3 b. */
export function formatSigma(barns: number | null | undefined): string {
  if (barns == null) return '—'
  if (barns !== 0 && Math.abs(barns) < 1e-3) return barns.toExponential(2)
  return trim(barns)
}

function trim(x: number): string {
  return Number(x.toPrecision(3)).toString()
}

/** GNDS name -> display form: "U235" -> "U-235", "Am242_m1" -> "Am-242m1". */
export function displayNuclide(gnds: string): string {
  const match = gnds.match(/^([A-Za-z]+)(\d+)(?:_m(\d+))?$/)
  if (!match) return gnds
  const [, symbol, a, meta] = match
  return `${symbol}-${a}${meta ? `m${meta}` : ''}`
}
