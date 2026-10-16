/*
  AWS-MMS developer documentation: page behaviour.
  Works from file:// with no server and no network: everything it needs is loaded by
  <script src> (Mermaid is vendored in assets/vendor/). No fetch() calls.
*/
(function () {
  'use strict'

  const root = document.documentElement
  const THEME_KEY = 'mms-docs-theme'

  // ---------- Storage (may be unavailable on file:// or in private windows) ----------
  function readPref () {
    try { return localStorage.getItem(THEME_KEY) || 'system' } catch { return 'system' }
  }
  function writePref (value) {
    try { localStorage.setItem(THEME_KEY, value) } catch { /* ignore */ }
  }

  // ---------- Theme ----------
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  let themePref = readPref()

  function isDark () {
    return themePref === 'dark' || (themePref === 'system' && media.matches)
  }

  function applyTheme (pref, { rerender = true } = {}) {
    themePref = pref
    if (pref === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', pref)
    for (const button of document.querySelectorAll('[data-theme-set]')) {
      button.setAttribute('aria-pressed', String(button.dataset.themeSet === pref))
    }
    if (rerender) renderAllDiagrams()
  }

  media.addEventListener('change', () => {
    if (themePref === 'system') renderAllDiagrams()
  })

  // ---------- Mermaid ----------
  let renderCount = 0

  function cssVar (name) {
    return getComputedStyle(root).getPropertyValue(name).trim()
  }

  function mermaidConfig () {
    const dark = isDark()
    const font = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'
    return {
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      fontFamily: font,
      // useMaxWidth: false keeps every diagram at its natural size (same text size everywhere);
      // wide diagrams scroll inside their panel and open full size with Expand.
      flowchart: { curve: 'basis', padding: 12, htmlLabels: true, useMaxWidth: false },
      sequence: { mirrorActors: false, actorMargin: 60, messageFontSize: 13, noteFontSize: 13, wrap: true, width: 170, useMaxWidth: false },
      er: { layoutDirection: 'TB', fontSize: 12, useMaxWidth: false },
      state: { padding: 8, useMaxWidth: false },
      themeVariables: {
        darkMode: dark,
        fontFamily: font,
        fontSize: '14px',
        background: cssVar('--surface'),
        primaryColor: cssVar('--primary-soft'),
        primaryBorderColor: cssVar('--primary'),
        primaryTextColor: cssVar('--fg'),
        secondaryColor: cssVar('--surface-2'),
        secondaryBorderColor: cssVar('--line-strong'),
        secondaryTextColor: cssVar('--fg'),
        tertiaryColor: cssVar('--surface'),
        tertiaryBorderColor: cssVar('--line-strong'),
        tertiaryTextColor: cssVar('--fg'),
        lineColor: cssVar('--muted'),
        textColor: cssVar('--fg'),
        mainBkg: cssVar('--primary-soft'),
        nodeBorder: cssVar('--primary'),
        clusterBkg: cssVar('--surface-2'),
        clusterBorder: cssVar('--line-strong'),
        titleColor: cssVar('--fg'),
        edgeLabelBackground: cssVar('--surface'),
        noteBkgColor: cssVar('--warn-bg'),
        noteBorderColor: cssVar('--warn'),
        noteTextColor: cssVar('--fg'),
        actorBkg: cssVar('--primary'),
        actorBorder: cssVar('--primary'),
        actorTextColor: cssVar('--on-primary'),
        actorLineColor: cssVar('--line-strong'),
        signalColor: cssVar('--fg-2'),
        signalTextColor: cssVar('--fg'),
        labelBoxBkgColor: cssVar('--surface-2'),
        labelBoxBorderColor: cssVar('--faint'),
        labelTextColor: cssVar('--fg'),
        loopTextColor: cssVar('--muted'),
        activationBkgColor: cssVar('--primary-soft'),
        activationBorderColor: cssVar('--primary'),
        sequenceNumberColor: cssVar('--on-primary'),
        stateBkg: cssVar('--primary-soft'),
        stateLabelColor: cssVar('--fg'),
        nodeTextColor: cssVar('--fg'),
        stateBorder: cssVar('--primary'),
        compositeBackground: cssVar('--surface-2'),
        altBackground: cssVar('--surface-2'),
        transitionColor: cssVar('--muted'),
        attributeBackgroundColorOdd: cssVar('--surface'),
        attributeBackgroundColorEven: cssVar('--surface-2'),
      },
    }
  }

  async function renderDiagram (holder) {
    const source = holder.dataset.source
    const target = holder.querySelector('.mermaid')
    try {
      const id = `mmd-${++renderCount}`
      const { svg } = await window.mermaid.render(id, source)
      target.innerHTML = svg
      applyFit(holder)
    } catch (error) {
      target.innerHTML = ''
      const message = document.createElement('p')
      message.className = 'render-error'
      message.textContent = `This diagram could not be drawn: ${error?.message || error}. Use "Source" to see the definition.`
      target.append(message)
      document.querySelectorAll('[id^="dmmd-"]').forEach(node => node.remove())
    }
  }

  // ---------- Diagram sizing: fit wide diagrams to the panel, never scale small ones up ----------
  function naturalWidth (canvas) {
    const svg = canvas.querySelector('.mermaid svg')
    if (svg) return Number.parseFloat(svg.getAttribute('width')) || svg.viewBox?.baseVal?.width || 0
    const img = canvas.querySelector('img')
    return img ? (img.naturalWidth || Number(img.getAttribute('width')) || 0) : 0
  }

  function isWide (canvas) {
    const style = getComputedStyle(canvas)
    const inner = canvas.clientWidth - Number.parseFloat(style.paddingLeft) - Number.parseFloat(style.paddingRight)
    return naturalWidth(canvas) > inner + 1
  }

  // canvas.dataset.zoom is 'fit' or 'actual' once the reader chooses; until then wide diagrams fit.
  function applyFit (canvas) {
    const choice = canvas.dataset.zoom
    const fit = choice ? choice === 'fit' : isWide(canvas)
    canvas.classList.toggle('fit', fit && isWide(canvas))
    canvas.closest('figure.diagram')?.dispatchEvent(new CustomEvent('diagram:sized'))
  }

  let renderQueue = Promise.resolve()
  function renderAllDiagrams () {
    if (!window.mermaid) return
    renderQueue = renderQueue.then(async () => {
      window.mermaid.initialize(mermaidConfig())
      for (const holder of document.querySelectorAll('[data-mermaid-holder]')) {
        await renderDiagram(holder)
      }
    })
    return renderQueue
  }

  // ---------- Diagram figures: tabs, source, expand ----------
  const dialog = document.getElementById('zoom')

  function makeButton (label, attrs = {}) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'btn'
    button.textContent = label
    for (const [key, value] of Object.entries(attrs)) button.setAttribute(key, value)
    return button
  }

  function setupFigures () {
    for (const figure of document.querySelectorAll('figure.diagram')) {
      const views = [...figure.querySelectorAll(':scope > .view')]

      // Turn each Mermaid definition into a render holder that keeps its source.
      for (const def of figure.querySelectorAll('pre.mermaid-def')) {
        const holder = document.createElement('div')
        holder.className = 'canvas'
        holder.dataset.mermaidHolder = ''
        holder.dataset.source = def.textContent.trim()
        const out = document.createElement('div')
        out.className = 'mermaid'
        const src = document.createElement('pre')
        src.className = 'mermaid-src'
        src.hidden = true
        src.textContent = holder.dataset.source
        holder.append(out, src)
        def.replaceWith(holder)
      }

      const bar = document.createElement('div')
      bar.className = 'diagram-bar'
      const title = document.createElement('div')
      title.className = 'diagram-title'
      title.textContent = figure.dataset.title || ''
      if (figure.dataset.kind) {
        const kind = document.createElement('span')
        kind.className = 'kind'
        kind.textContent = figure.dataset.kind
        title.append(kind)
      }
      const actions = document.createElement('div')
      actions.className = 'diagram-actions'

      let current = views[0]
      const tabButtons = []
      if (views.length > 1) {
        actions.setAttribute('role', 'tablist')
        views.forEach((view, index) => {
          const tab = makeButton(view.dataset.label || `View ${index + 1}`, { 'role': 'tab', 'aria-selected': String(index === 0) })
          tab.addEventListener('click', () => {
            views.forEach((v, i) => { v.hidden = i !== index; tabButtons[i].setAttribute('aria-selected', String(i === index)) })
            current = view
            syncSourceButton()
          })
          tabButtons.push(tab)
          actions.append(tab)
          view.hidden = index !== 0
        })
      }

      const sourceButton = makeButton('Source', { 'aria-pressed': 'false' })
      function syncSourceButton () {
        const holder = current?.querySelector('[data-mermaid-holder]')
        sourceButton.hidden = !holder
        const showing = holder && !holder.querySelector('.mermaid-src').hidden
        sourceButton.setAttribute('aria-pressed', String(Boolean(showing)))
      }
      sourceButton.addEventListener('click', () => {
        const holder = current?.querySelector('[data-mermaid-holder]')
        if (!holder) return
        const src = holder.querySelector('.mermaid-src')
        src.hidden = !src.hidden
        holder.querySelector('.mermaid').hidden = !src.hidden
        syncSourceButton()
      })

      // Fit / Actual size: shown only when the current view is wider than its panel.
      const sizeButton = makeButton('Actual size')
      function currentCanvas () {
        return current?.querySelector('.canvas')
      }
      function syncSizeButton () {
        const canvas = currentCanvas()
        const wide = Boolean(canvas) && isWide(canvas)
        sizeButton.hidden = !wide
        if (wide) sizeButton.textContent = canvas.classList.contains('fit') ? 'Actual size' : 'Fit'
      }
      sizeButton.addEventListener('click', () => {
        const canvas = currentCanvas()
        if (!canvas) return
        canvas.dataset.zoom = canvas.classList.contains('fit') ? 'actual' : 'fit'
        applyFit(canvas)
      })
      figure.addEventListener('diagram:sized', syncSizeButton)
      for (const img of figure.querySelectorAll('.canvas img')) {
        const fitImage = () => applyFit(img.closest('.canvas'))
        if (img.complete) fitImage()
        else img.addEventListener('load', fitImage)
      }
      for (const tab of tabButtons) tab.addEventListener('click', () => { const c = currentCanvas(); if (c) applyFit(c); syncSizeButton() })

      const expandButton = makeButton('Expand')
      expandButton.addEventListener('click', () => {
        const visual = current?.querySelector('.mermaid svg, img')
        if (!visual || !dialog) return
        dialog.querySelector('.zoom-title').textContent = figure.dataset.title || 'Diagram'
        const body = dialog.querySelector('.zoom-body')
        body.replaceChildren(visual.cloneNode(true))
        body.style.background = visual.tagName === 'IMG' ? '#FFFFFF' : ''
        dialog.showModal()
      })

      actions.append(sizeButton, sourceButton, expandButton)
      bar.append(title, actions)
      figure.prepend(bar)
      syncSourceButton()
    }

    dialog?.querySelector('[data-close]')?.addEventListener('click', () => dialog.close())
    dialog?.addEventListener('click', event => { if (event.target === dialog) dialog.close() })
  }

  // ---------- Copy buttons ----------
  function setupCopy () {
    for (const pre of document.querySelectorAll('pre.code')) {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'copy'
      button.textContent = 'Copy'
      button.addEventListener('click', async () => {
        const text = pre.querySelector('code')?.textContent ?? pre.textContent
        try {
          await navigator.clipboard.writeText(text)
          button.textContent = 'Copied'
        } catch {
          const range = document.createRange()
          range.selectNodeContents(pre.querySelector('code') || pre)
          const selection = window.getSelection()
          selection.removeAllRanges()
          selection.addRange(range)
          button.textContent = 'Selected'
        }
        setTimeout(() => { button.textContent = 'Copy' }, 1600)
      })
      pre.append(button)
    }
  }

  // ---------- Heading anchors ----------
  function setupAnchors () {
    for (const heading of document.querySelectorAll('main h2[id], main h3[id]')) {
      const link = document.createElement('a')
      link.className = 'anchor'
      link.href = `#${heading.id}`
      link.textContent = '#'
      link.setAttribute('aria-label', `Link to ${heading.textContent}`)
      heading.append(link)
    }
  }

  // ---------- Table filters ----------
  function setupTableFilters () {
    for (const tools of document.querySelectorAll('.table-tools[data-for]')) {
      const table = document.getElementById(tools.dataset.for)
      if (!table) continue
      const rows = [...table.tBodies[0].rows]
      const input = tools.querySelector('input')
      const select = tools.querySelector('select')
      const count = tools.querySelector('.count')
      const column = select ? Number(select.dataset.col) : -1
      function apply () {
        const terms = (input?.value || '').toLowerCase().split(/\s+/).filter(Boolean)
        const choice = select?.value || ''
        let shown = 0
        for (const row of rows) {
          const text = row.textContent.toLowerCase()
          const okText = terms.every(term => text.includes(term))
          const okChoice = !choice || (row.cells[column]?.textContent || '').toLowerCase().includes(choice.toLowerCase())
          row.hidden = !(okText && okChoice)
          if (!row.hidden) shown++
        }
        if (count) count.textContent = `${shown} of ${rows.length}`
      }
      input?.addEventListener('input', apply)
      select?.addEventListener('change', apply)
      apply()
    }
  }

  // ---------- Search ----------
  function setupSearch () {
    const input = document.getElementById('search')
    const list = document.getElementById('search-results')
    if (!input || !list) return

    const index = []
    for (const section of document.querySelectorAll('section.doc')) {
      const sectionTitle = section.querySelector('h2')?.firstChild?.textContent?.trim() || ''
      index.push({ id: section.id, title: sectionTitle, parent: '', text: section.querySelector('.doc-head')?.textContent || '' })
      for (const sub of section.querySelectorAll('.sub[id]')) {
        const title = sub.querySelector('h3')?.firstChild?.textContent?.trim() || sectionTitle
        index.push({ id: sub.id, title, parent: sectionTitle, text: sub.textContent })
      }
    }
    for (const entry of index) entry.haystack = `${entry.title} ${entry.text}`.toLowerCase().replace(/\s+/g, ' ')

    function snippet (text, term) {
      const flat = text.replace(/\s+/g, ' ').trim()
      const at = flat.toLowerCase().indexOf(term)
      if (at < 0) return flat.slice(0, 90)
      const start = Math.max(0, at - 30)
      return (start ? '…' : '') + flat.slice(start, at + 70)
    }

    function run () {
      const query = input.value.trim().toLowerCase()
      list.replaceChildren()
      if (query.length < 2) { list.hidden = true; return }
      const terms = query.split(/\s+/)
      const hits = index
        .filter(entry => terms.every(term => entry.haystack.includes(term)))
        .map(entry => ({ entry, score: (entry.title.toLowerCase().includes(terms[0]) ? 10 : 0) + (entry.parent ? 0 : 1) }))
        .sort((a, b) => b.score - a.score)
        .slice(0, 14)
      list.hidden = false
      if (!hits.length) {
        const empty = document.createElement('li')
        empty.className = 'search-empty'
        empty.textContent = 'No matches. Try a route, collection, event or ADR number.'
        list.append(empty)
        return
      }
      for (const { entry } of hits) {
        const item = document.createElement('li')
        const link = document.createElement('a')
        link.href = `#${entry.id}`
        link.textContent = entry.parent ? `${entry.parent} › ${entry.title}` : entry.title
        const small = document.createElement('small')
        small.textContent = snippet(entry.text, terms[0])
        link.append(small)
        link.addEventListener('click', () => { closeMenu() })
        item.append(link)
        list.append(item)
      }
    }

    input.addEventListener('input', run)
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        const first = list.querySelector('a')
        if (first) { location.hash = first.getAttribute('href'); closeMenu() }
      } else if (event.key === 'Escape') {
        input.value = ''
        run()
      }
    })
    document.addEventListener('keydown', event => {
      if (event.key === '/' && !/input|textarea|select/i.test(document.activeElement?.tagName || '')) {
        event.preventDefault()
        openMenu()
        input.focus()
      }
    })
  }

  // ---------- Navigation: scroll spy and mobile menu ----------
  const sidebar = document.querySelector('.sidebar')
  const menuButton = document.querySelector('.menu-toggle')
  function openMenu () { if (sidebar && menuButton && getComputedStyle(menuButton).display !== 'none') { sidebar.classList.add('open'); menuButton.setAttribute('aria-expanded', 'true') } }
  function closeMenu () { if (sidebar?.classList.contains('open')) { sidebar.classList.remove('open'); menuButton?.setAttribute('aria-expanded', 'false') } }

  function setupNav () {
    menuButton?.addEventListener('click', () => {
      if (sidebar.classList.contains('open')) closeMenu()
      else openMenu()
    })
    for (const link of document.querySelectorAll('.toc a')) link.addEventListener('click', closeMenu)

    const links = new Map([...document.querySelectorAll('.toc a')].map(a => [a.getAttribute('href').slice(1), a]))
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        for (const link of links.values()) link.removeAttribute('aria-current')
        links.get(entry.target.id)?.setAttribute('aria-current', 'true')
      }
    }, { rootMargin: '-10% 0px -75% 0px' })
    for (const section of document.querySelectorAll('section.doc')) observer.observe(section)
  }

  // ---------- Start ----------
  function start () {
    applyTheme(themePref, { rerender: false })
    for (const button of document.querySelectorAll('[data-theme-set]')) {
      button.addEventListener('click', () => { writePref(button.dataset.themeSet); applyTheme(button.dataset.themeSet) })
    }
    setupFigures()
    setupCopy()
    setupAnchors()
    setupTableFilters()
    setupSearch()
    setupNav()
    let resizeTimer
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => document.querySelectorAll('figure.diagram .canvas').forEach(applyFit), 150)
    })
    renderAllDiagrams()?.then(() => {
      // Re-apply a deep link once diagrams have changed the page height.
      if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView()
    })
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start)
  else start()
})()
