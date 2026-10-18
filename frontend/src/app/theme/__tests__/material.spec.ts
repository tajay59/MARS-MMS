import { describe, expect, it } from 'vitest'
import { buildThemes, builtInMaterial } from '@/app/theme/brand'
import { contrast, contrastProblems, materialColors, PALETTES, parseMaterialTheme, ROLES, toExportJson, TONES } from '@/app/theme/material'
import builtInFile from '@/app/theme/material-theme.json'
import { generateMaterialTheme } from '@/app/theme/materialGenerate'

// Brand colours from a Material 3 theme (decision W4-12, DBD "Colour palette")
describe('parseMaterialTheme', () => {
  it('reads a Material Theme Builder export and keeps only what the app uses', () => {
    const parsed = parseMaterialTheme(builtInFile, 'Built-in')
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) {
      return
    }
    expect(Object.keys(parsed.theme.schemes)).toEqual(['light', 'dark'])
    expect(Object.keys(parsed.theme.schemes.light!)).toEqual([...ROLES])
    expect(Object.keys(parsed.theme.palettes)).toEqual([...PALETTES])
    expect(Object.keys(parsed.theme.palettes.primary!)).toEqual([...TONES])
    expect(parsed.theme.name).toBe('Built-in')
    expect(parsed.theme.seed).toBe('#026D88')
  })

  it('names what is missing', () => {
    const broken = structuredClone(builtInFile) as Record<string, any>
    delete broken.schemes.dark.outline
    expect(parseMaterialTheme(broken)).toEqual({ ok: false, error: 'The dark scheme needs outline as a colour like #0A6780.' })
    expect(parseMaterialTheme({ hello: 1 }).ok).toBe(false)
    expect(parseMaterialTheme(null).ok).toBe(false)
  })

  it('refuses anything that is not #RRGGBB, so only colours reach the CSS variables', () => {
    const broken = structuredClone(builtInFile) as Record<string, any>
    broken.schemes.light.primary = 'red; background: url(x)'
    expect(parseMaterialTheme(broken).ok).toBe(false)
  })

  it('round-trips through the exported file', () => {
    const again = parseMaterialTheme(JSON.parse(toExportJson(builtInMaterial)))
    expect(again).toEqual({ ok: true, theme: builtInMaterial })
  })
})

describe('materialColors', () => {
  it('maps the built-in theme onto the DBD tokens', () => {
    const light = materialColors(builtInMaterial, false)
    expect(light.primary).toBe('#0A6780')
    expect(light.surface).toBe('#FFFFFF') // tiles: surfaceContainerLowest
    expect(light.ground).toBe('#EAEEF2') // surfaceContainer
    expect(light['primary-600']).toBe(builtInMaterial.palettes.primary!['40'])
    const dark = materialColors(builtInMaterial, true)
    expect(dark.primary).toBe('#89D0ED')
    expect(dark.surface).toBe('#171C1F') // surfaceContainerLow
    expect(dark.ground).toBe('#0A0F11') // surfaceContainerLowest
  })

  it('keeps the status colours fixed whatever the theme', () => {
    const red = generateMaterialTheme('#D00000')
    const a = buildThemes(builtInMaterial)
    const b = buildThemes(red)
    for (const key of ['status-closed', 'on-status-denied', 'station-offline', 'success', 'warning']) {
      expect(b.light.colors![key]).toBe(a.light.colors![key])
      expect(b.dark.colors![key]).toBe(a.dark.colors![key])
    }
    expect(b.light.colors!.primary).not.toBe(a.light.colors!.primary)
  })

  it('gives the built-in theme readable text in both themes (WCAG 1.4.3)', () => {
    expect(contrastProblems(builtInMaterial)).toEqual([])
  })

  it('keeps white avatar initials at 4.5:1 on every gradient stop', () => {
    for (const dark of [false, true]) {
      const c = materialColors(builtInMaterial, dark)
      for (const stop of ['primary-600', 'primary-700', 'secondary-600', 'secondary-700', 'tertiary-600', 'tertiary-700']) {
        expect(contrast('#FFFFFF', c[stop]!)).toBeGreaterThanOrEqual(4.5)
      }
    }
  })
})

describe('generateMaterialTheme', () => {
  it('makes a complete theme from one colour that the server would accept', () => {
    const theme = generateMaterialTheme('#026d88', 'Teal')
    const parsed = parseMaterialTheme(theme)
    expect(parsed).toEqual({ ok: true, theme })
    expect(theme.seed).toBe('#026D88')
    expect(contrastProblems(theme)).toEqual([])
  })
})

describe('contrast', () => {
  it('follows WCAG 2.x', () => {
    expect(contrast('#000000', '#FFFFFF')).toBeCloseTo(21, 0)
    expect(contrast('#777777', '#FFFFFF')).toBeCloseTo(4.48, 1)
  })
})
