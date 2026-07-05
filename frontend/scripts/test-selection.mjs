// Regression test for the selection-reset bug: pick Th-227 in the XS view,
// navigate away through the top bar and back, and assert the nuclide (and
// MT) survived. Run with the backend on :8000 and Vite on :5173:
//   HS=<path-to-headless-shell> node scripts/test-selection.mjs
import { chromium } from 'playwright-core'

const browser = await chromium.launch({ executablePath: process.env.HS })
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
const fail = (msg) => {
  console.error(`FAIL: ${msg}`)
  process.exitCode = 1
}

await page.goto('http://localhost:5173/xs', { waitUntil: 'networkidle' })
await page.fill('input[list="nide-nuclides"]', 'Th227')
await page.waitForTimeout(2500)
// Pick a non-default reaction too: MT must persist along with the nuclide.
await page.selectOption('select', { value: '102' }).catch(() => {})
await page.waitForTimeout(1500)

await page.click('text=Compare')
await page.waitForTimeout(2000)
const compareNuclide = await page.inputValue('input[list="nide-nuclides"]')
if (compareNuclide !== 'Th227') fail(`Compare shows '${compareNuclide}', expected Th227`)

await page.click('text=Decay Chains')
await page.waitForTimeout(1500)
const decayNuclide = await page.inputValue('input[list="nide-nuclides"]')
if (decayNuclide !== 'Th227') fail(`Decay shows '${decayNuclide}', expected Th227`)

await page.click('text=Cross Sections')
await page.waitForTimeout(1500)
const backNuclide = await page.inputValue('input[list="nide-nuclides"]')
if (backNuclide !== 'Th227') fail(`XS after round-trip shows '${backNuclide}', expected Th227`)
const backMt = await page.inputValue('select')
if (backMt !== '102') fail(`XS after round-trip shows MT=${backMt}, expected 102`)

console.log(process.exitCode ? 'SELECTION TEST FAILED' : 'SELECTION PERSISTS ACROSS VIEWS ✓')
await browser.close()
