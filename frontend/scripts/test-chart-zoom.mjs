// Regression test (bug: zoom reset on hover after wheel-zoom). Run with
// backend on :8000 and Vite on :5173:
//   HS=<path-to-headless-shell> node scripts/test-chart-zoom.mjs
// Regression check for the zoom-reset bug: after wheel-zooming, moving the
// mouse (which changes hover state) must NOT reset the view to the initial
// fit. At high zoom two points 60px apart hover *adjacent* nuclides; at the
// initial fit scale (~6px/cell) they are ~10 cells apart.
import { chromium } from 'playwright-core'

const browser = await chromium.launch({ executablePath: process.env.HS })
const page = await browser.newPage({ viewport: { width: 1560, height: 980 } })
page.on('pageerror', (e) => console.log('PAGEERROR', String(e).slice(0, 200)))

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(4000)

const canvas = await page.locator('canvas').boundingBox()
const cx = canvas.x + canvas.width * 0.3
const cy = canvas.y + canvas.height * 0.7

// Zoom in hard at (cx, cy).
await page.mouse.move(cx, cy)
for (let i = 0; i < 16; i++) {
  await page.mouse.wheel(0, -240)
  await page.waitForTimeout(50)
}
// THE TRIGGER: wander the mouse around after zooming (changes hover state).
for (const [dx, dy] of [[40, 10], [-30, 50], [80, -40], [10, 20], [0, 0]]) {
  await page.mouse.move(cx + dx, cy + dy)
  await page.waitForTimeout(300)
}

const hoverAt = async (x, y) => {
  await page.mouse.move(x, y)
  await page.waitForTimeout(400)
  const text = await page.locator('section:has(h2:text("Hover")) p.text-base').textContent().catch(() => null)
  return text?.trim() ?? null
}
const a = await hoverAt(cx, cy)
const b = await hoverAt(cx + 60, cy)
console.log('hover at P:', a, '| hover at P+60px:', b)

const parse = (s) => {
  const m = s?.match(/^([A-Za-z]+)-(\d+)/)
  return m ? { sym: m[1], a: Number(m[2]) } : null
}
const pa = parse(a)
const pb = parse(b)
if (!pa || !pb) {
  console.log('FAIL: no nuclide under cursor (view lost?)')
  process.exitCode = 1
} else {
  const massDelta = Math.abs(pa.a - pb.a)
  if (massDelta > 3) {
    console.log(`FAIL: 60px spans ${massDelta} mass units — view reset to fit scale`)
    process.exitCode = 1
  } else {
    console.log(`ZOOM PERSISTS AFTER HOVER ✓ (60px spans ${massDelta} mass units)`)
  }
}
await page.screenshot({ path: '../docs/screenshots/chart_zoom_high.png' })
await browser.close()
