import vuetify from 'eslint-config-vuetify'

export default [
  // Generated from openapi/*.json by `npm run api:types`
  { ignores: ['src/api/types/**', 'dev-dist/**', 'playwright-report/**', 'test-results/**'] },
  ...await vuetify({
    ts: true,
  }),
]
