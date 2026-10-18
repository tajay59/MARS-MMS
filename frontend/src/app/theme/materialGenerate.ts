import type { MaterialTheme, Palette, PaletteName, Role, Scheme } from './material'
import {
  argbFromHex,
  type DynamicScheme,
  Hct,
  hexFromArgb,
  SchemeTonalSpot,
  type TonalPalette,
} from '@material/material-color-utilities'
import { PALETTES, ROLES, TONES } from './material'

/*
  A whole Material 3 theme from one seed colour, the way Material Theme Builder makes one
  (tonal spot, standard contrast). Only the Settings page loads this, so the library stays out of
  the app's first download.
*/

function schemeOf (dynamic: DynamicScheme): Scheme {
  const out = {} as Scheme
  const roles = dynamic as unknown as Record<Role, number>
  for (const role of ROLES) {
    out[role] = hexFromArgb(roles[role]).toUpperCase()
  }
  return out
}

function paletteOf (palette: TonalPalette): Palette {
  const out = {} as Palette
  for (const tone of TONES) {
    out[tone] = hexFromArgb(palette.tone(Number(tone))).toUpperCase()
  }
  return out
}

export function generateMaterialTheme (seed: string, name: string | null = null): MaterialTheme {
  const hct = Hct.fromInt(argbFromHex(seed))
  const light = new SchemeTonalSpot(hct, false, 0)
  const dark = new SchemeTonalSpot(hct, true, 0)
  const sources: Record<PaletteName, TonalPalette> = {
    'primary': light.primaryPalette,
    'secondary': light.secondaryPalette,
    'tertiary': light.tertiaryPalette,
    'neutral': light.neutralPalette,
    'neutral-variant': light.neutralVariantPalette,
  }
  const palettes = {} as Record<PaletteName, Palette>
  for (const p of PALETTES) {
    palettes[p] = paletteOf(sources[p])
  }
  return {
    name,
    seed: seed.toUpperCase(),
    schemes: { light: schemeOf(light), dark: schemeOf(dark) },
    palettes,
  }
}
