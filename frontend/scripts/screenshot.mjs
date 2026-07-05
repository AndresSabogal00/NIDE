// E2E smoke test + README screenshots: load every NIDE view with real data,
// capture PNGs, and report console/page/HTTP errors. Temporary tooling file.
import { chromium } from 'playwright-core'

const VIEWS = [
  ['chart', 'http://localhost:5173/', 9000],
  ['xs_viewer', 'http://localhost:5173/xs?nuclide=U235&mt=18&libs=endfb80,jeff33,jendl5&exfor=1', 12000],
  ['comparison', 'http://localhost:5173/compare?nuclide=U238&mt=102', 12000],
  ['decay', 'http://localhost:5173/decay?nuclide=U238', 8000],
  ['yields', 'http://localhost:5173/yields?nuclide=U235', 8000],
]

const browser = await chromium.launch({ executablePath: process.env.HS })
const page = await browser.newPage({ viewport: { width: 1560, height: 980 } })
const errors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(`[console] ${msg.text().slice(0, 300)}`)
})
page.on('pageerror', (err) => errors.push(`[pageerror] ${String(err).slice(0, 300)}`))
page.on('response', (res) => {
  if (res.status() >= 400 && res.url().includes('/api/')) errors.push(`[http ${res.status()}] ${res.url()}`)
})

for (const [name, url, wait] of VIEWS) {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch((e) => errors.push(`[goto ${name}] ${e}`))
  await page.waitForTimeout(wait)
  await page.screenshot({ path: `../docs/screenshots/${name}.png` })
  console.log(`shot: ${name}`)
}
await browser.close()
if (errors.length) {
  console.log('--- ERRORS ---')
  for (const e of [...new Set(errors)]) console.log(e)
} else console.log('NO BROWSER ERRORS')
