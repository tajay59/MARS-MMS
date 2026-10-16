// Sets the dark class before first paint so there is no light flash.
// Loaded as an external script because the CSP is script-src 'self'.
// Keep the storage key and logic in step with src/app/theme/preference.ts.
(function () {
  let preference = 'system'
  try {
    preference = localStorage.getItem('mms-theme') || 'system'
  } catch {
    // Storage blocked (private mode): fall back to the system setting
  }
  const dark = preference === 'dark'
    || (preference === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  if (dark) {
    document.documentElement.classList.add('app-dark')
  }
})()
