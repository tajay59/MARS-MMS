// Builds the app's logo files and PWA icons from the source PNGs in ../logo (DBD D1).
// Run from frontend/ after the logo changes: `node scripts/brand-assets.mjs`, then commit the output.
// The sources are raster; when an SVG of the logo exists, point MARK and WORDMARK at it.

import { mkdir, writeFile } from 'node:fs/promises'
import sharp from 'sharp'
import ico from 'sharp-ico'

const MARK = '../logo/logo.png' // the round mark on its own, transparent background
const WORDMARK = '../logo/logo_text.png' // "MARS MMS" lettering, navy, transparent background
const ICON_BACKGROUND = '#22569A' // primary-600: DBD "the PWA icon is a square mark on primary-600"

// Palette PNGs: the AI-made sources carry pixel noise that full-colour PNG can't compress.
const PNG = { compressionLevel: 9, palette: true, quality: 90 }

const ui = 'src/assets/brand'
const pub = 'public'
await mkdir(ui, { recursive: true })

// The mark, trimmed and made square so it centres in round and square slots.
const trimmed = await sharp(MARK).trim().toBuffer({ resolveWithObject: true })
const side = Math.max(trimmed.info.width, trimmed.info.height)
const square = await sharp(trimmed.data)
  .resize(side, side, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
  .png()
  .toBuffer()

/** The mark at `size` px, its circle filling `scale` of the canvas, on `background` (transparent if none). */
async function icon (size, scale, background) {
  const inner = Math.round(size * scale)
  const mark = await sharp(square).resize(inner, inner).toBuffer()
  return sharp({
    create: { width: size, height: size, channels: 4, background: background ?? { r: 0, g: 0, b: 0, alpha: 0 } },
  })
    .composite([{ input: mark, gravity: 'centre' }])
    .png(PNG)
    .toBuffer()
}

// In the UI the mark shows at 28–48 px; 160 px covers 3x screens.
await writeFile(`${ui}/mark.png`, await sharp(square).resize(160, 160).png(PNG).toBuffer())

// The wordmark: navy for light surfaces, white (same shape) for the dark panel and dark theme.
const word = await sharp(WORDMARK).trim().resize({ height: 96 }).ensureAlpha().toBuffer({ resolveWithObject: true })
await writeFile(`${ui}/wordmark.png`, await sharp(word.data).png(PNG).toBuffer())
const alpha = await sharp(word.data).extractChannel('alpha').toBuffer()
const white = await sharp({
  create: { width: word.info.width, height: word.info.height, channels: 3, background: '#FFFFFF' },
})
  .joinChannel(alpha)
  .png(PNG)
  .toBuffer()
await writeFile(`${ui}/wordmark-white.png`, white)

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
