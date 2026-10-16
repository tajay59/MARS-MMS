// Applies the saved theme before first paint, so the page doesn't flash the wrong theme.
(function () {
  try {
    var pref = localStorage.getItem('mms-docs-theme')
    if (pref === 'light' || pref === 'dark') document.documentElement.setAttribute('data-theme', pref)
  } catch (e) { /* storage unavailable: follow the system setting */ }
})()
