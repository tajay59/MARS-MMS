# AWS-MMS frontend

Vue 3 + TypeScript PWA built with Vite, Vuetify 4 and Tailwind CSS 4. The rules are in the repository's [CLAUDE.md](../CLAUDE.md); the design source of truth is [docs/DBD.md](../docs/DBD.md) and the conventions are TRD §13.

## Commands

```sh
npm install
npm run dev          # dev server on http://localhost:3000
npm run type-check   # vue-tsc
npm run lint         # ESLint (eslint-config-vuetify)
npm run build        # type-check + production build
```

## Theme foundation

| File | Purpose |
|---|---|
| `src/app/theme/brand.ts` | Light and dark Vuetify themes from the DBD tokens |
| `src/app/theme/vuetify.ts` | The single `createVuetify` call: themes, global defaults, MDI SVG icons, display thresholds |
| `src/app/theme/icons.ts` | The icons the app uses, imported from `@mdi/js` |
| `src/app/theme/tailwind.css` | Tailwind theme mapped to `--v-theme-*`, type scale, `dark:` on `.app-dark` |
| `src/app/theme/layers.css` | Cascade layer order; imported first |
| `src/app/theme/settings.scss` | Vuetify Sass settings: utility and colour classes off, Tailwind breakpoints |
| `public/theme-init.js` | Sets `.app-dark` before first paint (external because of the CSP) |
| `src/stores/theme.ts` | Light / Dark / System preference |
