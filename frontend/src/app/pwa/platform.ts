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

/**
 * "iPhone, iOS 18.0, Safari" or "Android 15, Chrome": enough to tell phones apart in a bug report
 * (the diagnostics block on /sync). Read from the user agent, so it is a hint, not a promise.
 */
export function describePhone (nav: Navigator = navigator): string {
  const ua = nav.userAgent
  let system = 'Computer'
  const ios = /OS (\d+)[_.](\d+)/.exec(ua)
  const android = /Android (\d+)/.exec(ua)
  if (isIos(nav)) {
    const device = /iPad/.test(ua) || (nav.platform === 'MacIntel' && !/iPhone/.test(ua)) ? 'iPad' : 'iPhone'
    system = ios ? `${device}, iOS ${ios[1]}.${ios[2]}` : device
  } else if (android) {
    system = `Android ${android[1]}`
  }
  let browser = 'browser'
  if (/Edg\//.test(ua)) {
    browser = 'Edge'
  } else if (/Firefox|FxiOS/.test(ua)) {
    browser = 'Firefox'
  } else if (/Chrome|CriOS/.test(ua)) {
    browser = 'Chrome'
  } else if (/Safari/.test(ua)) {
    browser = 'Safari'
  }
  return `${system}, ${browser}`
}
