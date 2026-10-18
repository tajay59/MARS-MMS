/* eslint-disable perfectionist/sort-imports -- stylesheet order is significant */
// The cascade layer order is fixed by public/layers.css, linked first in index.html (TRD §13.2).
// Fonts, then Tailwind, then base.css; vuetify/styles comes with ./app/theme/vuetify.
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
