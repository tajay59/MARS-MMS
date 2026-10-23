/*
  What kind of phone and window this is, for the few places the app behaves differently (pwa skill
  ios-safari.md). Feature checks are better where a feature exists; these are for the two facts
  that have no feature to test: iOS keeps an installed app's storage apart from Safari's (finding
  F2), and an installed app runs in its own window.
*/

interface IosNavigator extends Navigator {
  standalone?: boolean
}

export function isIos (nav: Navigator = navigator): boolean {
  // iPadOS 13+ says it is a Mac; a Mac has no touch screen
  return /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1)
}

/** Running as an installed app (Home Screen on iOS, an installed PWA elsewhere). */
export function isStandalone (nav: Navigator = navigator, media: Pick<Window, 'matchMedia'> = globalThis): boolean {
  return (nav as IosNavigator).standalone === true || Boolean(media.matchMedia?.('(display-mode: standalone)').matches)
}

/**
 * On an iPhone, a visit prepared in a Safari tab would be invisible to the Home Screen app and
 * subject to Safari's seven-day clean-up: install first (F2, W13-12).
 */
export function mustInstallToPrepare (nav: Navigator = navigator, media: Pick<Window, 'matchMedia'> = globalThis): boolean {
  return isIos(nav) && !isStandalone(nav, media)
}
