/*
  The product name and logo files shown in the app (DBD D1). `npm run brand` (scripts/brand-assets.mjs)
  builds the logo files from the SVGs in /logo.
*/

import mark from '@/assets/brand/mark.svg'
import wordmarkWhite from '@/assets/brand/wordmark-white.svg'
import wordmark from '@/assets/brand/wordmark.svg'

export const APP_NAME = 'MARS-MMS'
export const APP_LONG_NAME = 'Automatic Weather Station Maintenance Management System'
/** The release (frontend/package.json), so a phone shows which build it runs. */
export const APP_VERSION = __APP_VERSION__

export const logo = { mark, wordmark, wordmarkWhite }
