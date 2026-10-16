/* eslint-disable perfectionist/sort-imports -- stylesheet order is significant */
// The cascade layer order must be declared before any other stylesheet, including
// vuetify/styles imported by ./app/theme/vuetify (TRD §13.2). Don't reorder these imports.
import './app/theme/layers.css'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './app/theme/tailwind.css'
import './app/theme/base.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './app/router'
import vuetify from './app/theme/vuetify'

createApp(App)
  .use(vuetify)
  .use(createPinia())
  .use(router)
  .mount('#app')
