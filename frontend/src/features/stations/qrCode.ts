import { create } from 'qrcode'

/*
  The station's QR code, drawn in the browser from its token (QR-1, QR-7). The picture is built as
  one SVG path from the code's modules, so nothing is injected as HTML. The library is loaded
  only when a station's card opens (a dynamic import), so it stays out of the app chunk.
*/

export interface QrPicture {
  /** Modules per side, without the quiet zone (the page adds it with the viewBox). */
  size: number
  /** One path of 1 x 1 squares for the dark modules. */
  path: string
}

export function qrPicture (text: string): QrPicture {
  const { modules } = create(text, { errorCorrectionLevel: 'M' })
  const size = modules.size
  const squares: string[] = []
  for (let y = 0; y < size; y++) {
    // Runs of dark modules on a row become one rectangle each: a smaller path
    let x = 0
    while (x < size) {
      if (modules.get(y, x)) {
        const start = x
        while (x < size && modules.get(y, x)) {
          x++
        }
        squares.push(`M${start} ${y}h${x - start}v1h-${x - start}z`)
      } else {
        x++
      }
    }
  }
  return { size, path: squares.join('') }
}
