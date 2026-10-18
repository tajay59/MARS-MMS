// Builds the app's logo files and PWA icons from the source SVGs in ../logo (DBD D1).
// Run from frontend/ after the logo changes: `node scripts/brand-assets.mjs`, then commit the output.
//
// The sources are traced vectors (absolute M/C/L/z paths only) with a C2PA manifest in <metadata>.
// The UI files are cleaned copies: metadata and near-transparent tracing specks dropped, numbers
// rounded, viewBox trimmed to the drawing. The wordmark has no SVG of its own; it is the lettering
// cut from the stacked logo (every path below the mark).

import { mkdir, readFile, writeFile } from 'node:fs/promises'
import sharp from 'sharp'
import ico from 'sharp-ico'

const MARK = '../logo/logo.svg' // the round mark on its own
const STACKED = '../logo/logo_main.svg' // the mark above "MARS MMS"; the wordmark is cut from it
const WORDMARK_TOP = 1450 // in STACKED's units: the mark ends near y 1300, the lettering starts near y 1600
// primary-600 (tone 40 of the built-in Material theme): DBD "the PWA icon is a square mark on primary-600"
const theme = JSON.parse(await readFile('src/app/theme/material-theme.json', 'utf8'))
const ICON_BACKGROUND = theme.palettes.primary['40']

const PNG = { compressionLevel: 9, palette: true, quality: 90 }

const ui = 'src/assets/brand'
const pub = 'public'
await mkdir(ui, { recursive: true })

/** The visible paths of a traced SVG, each with its fill (hex), rounded `d` and bounding box. */
async function paths (file) {
  const svg = await readFile(file, 'utf8')
  const out = []
  for (const [, attrs] of svg.matchAll(/<path\b([^>]*)\/>/g)) {
    const opacity = Number(/fill-opacity="([\d.]+)"/.exec(attrs)?.[1] ?? 1)
    if (opacity < 0.5) {
      continue
    } // anti-aliasing specks left by the tracer
    const [r, g, b] = /fill="rgb\((\d+),(\d+),(\d+)\)"/.exec(attrs).slice(1).map(Number)
    const d = /\bd="([^"]*)"/.exec(attrs)[1].replace(/-?\d+(?:\.\d+)?/g, n => String(Math.round(Number(n) * 10) / 10))
    // Absolute commands only, so every number pair is a point (control points make the box a touch generous).
    const nums = d.match(/-?\d+(?:\.\d+)?/g).map(Number)
    const xs = nums.filter((_, i) => i % 2 === 0)
    const ys = nums.filter((_, i) => i % 2 === 1)
    out.push({
      fill: '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join(''),
      d,
      box: { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) },
    })
  }
  return out
}

/** An SVG of `list` with its viewBox trimmed to them (made square if asked), every fill `fill` if given. */
function svgOf (list, { square = false, fill } = {}) {
  let x0 = Math.min(...list.map(p => p.box.x0))
  let y0 = Math.min(...list.map(p => p.box.y0))
  let w = Math.max(...list.map(p => p.box.x1)) - x0
  let h = Math.max(...list.map(p => p.box.y1)) - y0
  if (square) {
    const side = Math.max(w, h)
    x0 -= (side - w) / 2
    y0 -= (side - h) / 2
    w = h = side
  }
  const box = [x0, y0, w, h].map(n => Math.round(n * 10) / 10).join(' ')
  const body = list.map(p => `<path fill="${fill ?? p.fill}" d="${p.d}"/>`).join('')
  return { svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box}">${body}</svg>\n`, ratio: w / h }
}

// The mark, square so it centres in round and square slots.
const mark = svgOf(await paths(MARK), { square: true })
await writeFile(`${ui}/mark.svg`, mark.svg)

// The wordmark: navy for light surfaces, white (same shape) for the dark panel and dark theme.
const lettering = (await paths(STACKED)).filter(p => p.box.y0 > WORDMARK_TOP)
const word = svgOf(lettering)
await writeFile(`${ui}/wordmark.svg`, word.svg)
await writeFile(`${ui}/wordmark-white.svg`, svgOf(lettering, { fill: '#ffffff' }).svg)

// A large raster of the mark for the icons below.
const square = await sharp(Buffer.from(mark.svg)).resize(1024, 1024).png().toBuffer()

/** The mark at `size` px, its circle filling `scale` of the canvas, on `background` (transparent if none). */
async function icon (size, scale, background) {
  const inner = Math.round(size * scale)
  const m = await sharp(square).resize(inner, inner).toBuffer()
  return sharp({
    create: { width: size, height: size, channels: 4, background: background ?? { r: 0, g: 0, b: 0, alpha: 0 } },
  })
    .composite([{ input: m, gravity: 'centre' }])
    .png(PNG)
    .toBuffer()
}

// PWA icons (manifest-install.md §2): transparent "any" icons, plus opaque maskable and Apple icons
// with the mark inside the safe zone (Android crops to a circle; iOS fills transparency with black).
await writeFile(`${pub}/pwa-64x64.png`, await icon(64, 0.96))
await writeFile(`${pub}/pwa-192x192.png`, await icon(192, 0.96))
await writeFile(`${pub}/pwa-512x512.png`, await icon(512, 0.96))
await writeFile(`${pub}/maskable-icon-512x512.png`, await icon(512, 0.7, ICON_BACKGROUND))
await writeFile(`${pub}/apple-touch-icon-180x180.png`, await icon(180, 0.78, ICON_BACKGROUND))
await ico.sharpsToIco(
  [16, 32, 48].map(size => sharp(square).resize(size, size)),
  `${pub}/favicon.ico`,
)

console.log('Brand assets written to', ui, 'and', pub)
console.log('Wordmark width ÷ height (WORDMARK_RATIO in components/AppLogo.vue):', word.ratio.toFixed(4))
