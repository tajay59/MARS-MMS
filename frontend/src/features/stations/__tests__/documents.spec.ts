import { describe, expect, it, vi } from 'vitest'
import {
  docState,
  docTypeLabel,
  documentKind,
  extensionOf,
  failReason,
  fileIcon,
  fileProblem,
  formatBytes,
  openDownload,
  percent,
  titleFromFilename,
  versionText,
} from '../documents'

const MB = 1024 * 1024

describe('files', () => {
  it('reads the extension in lower case, and none from a dotfile', () => {
    expect(extensionOf('Plan.PDF')).toBe('.pdf')
    expect(extensionOf('archive.tar.gz')).toBe('.gz')
    expect(extensionOf('.hidden')).toBe('')
    expect(extensionOf('README')).toBe('')
  })

  it('files a PDF as pdf and anything else media accepts as document', () => {
    expect(documentKind('a.pdf')).toBe('pdf')
    expect(documentKind('a.DOCX')).toBe('document')
    expect(documentKind('photo.jpg')).toBe('document')
  })

  it('refuses an empty file, one over 50 MB and a type documents do not take', () => {
    expect(fileProblem({ name: 'a.pdf', size: 0 }, 'document')).toMatch(/empty/)
    expect(fileProblem({ name: 'a.pdf', size: 51 * MB }, 'document')).toMatch(/50 MB/)
    expect(fileProblem({ name: 'tool.exe', size: 10 }, 'document')).toMatch(/\.exe/)
    expect(fileProblem({ name: 'notes', size: 10 }, 'document')).toMatch(/This kind of/)
    expect(fileProblem({ name: 'a.pdf', size: 50 * MB }, 'document')).toBeNull()
  })

  it('lets a configuration set take any type but the ones an operating system runs', () => {
    expect(fileProblem({ name: 'KINGSTON.CR1X', size: 10 }, 'config')).toBeNull()
    expect(fileProblem({ name: 'no-extension', size: 10 }, 'config')).toBeNull()
    expect(fileProblem({ name: 'update.exe', size: 10 }, 'config')).toBe('.exe files can’t be uploaded here.')
    expect(fileProblem({ name: 'page.HTML', size: 10 }, 'config')).toMatch(/\.html/)
  })

  it('writes sizes the way a file list does', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(48 * 1024)).toBe('48 KB')
    expect(formatBytes(Math.round(1.8 * MB))).toBe('1.8 MB')
    expect(formatBytes(120 * MB)).toBe('120 MB')
  })

  it('offers a title from the file name', () => {
    expect(titleFromFilename('kin-power_wiring.pdf')).toBe('kin power wiring')
    expect(titleFromFilename('Site  drawing  rev C.docx')).toBe('Site drawing rev C')
    expect(titleFromFilename('plain')).toBe('plain')
  })

  it('picks an icon by type, red for a PDF', () => {
    expect(fileIcon('a.pdf').tone).toBe('text-error')
    expect(fileIcon('a.xlsx').tone).toBe('text-surface-600')
    expect(fileIcon('a.unknown').icon).toBe(fileIcon('b.other').icon)
    expect(fileIcon('a.pdf').icon).not.toBe(fileIcon('a.xlsx').icon)
  })
})

describe('documents', () => {
  it('names the types, and passes an unknown one through', () => {
    expect(docTypeLabel('site_drawing')).toBe('Site drawing')
    expect(docTypeLabel('operations_manual')).toBe('Operations manual')
    expect(docTypeLabel('mystery')).toBe('mystery')
  })

  it('is downloadable only once media has passed it', () => {
    expect(docState({ status: 'available' })).toBe('ready')
    expect(docState({ status: 'pending' })).toBe('checking')
    expect(docState({ status: 'failed' })).toBe('failed')
  })

  it('shows the label, never the record counter', () => {
    expect(versionText({ version_label: 'Rev C' })).toBe('Rev C')
    expect(versionText({ version_label: '  ' })).toBe('—')
    expect(versionText({ version_label: null })).toBe('—')
  })

  it('explains a failed check in words', () => {
    expect(failReason('infected')).toMatch(/virus/)
    expect(failReason(null)).toMatch(/did not pass/)
  })

  it('never shows 100% before the server holds the file', () => {
    expect(percent(0, 100)).toBe(0)
    expect(percent(50, 100)).toBe(50)
    expect(percent(100, 100)).toBe(99)
    expect(percent(100, 100, true)).toBe(100)
    expect(percent(5, 0)).toBe(0)
  })
})

describe('openDownload', () => {
  it('opens a tab in the click for a file the browser shows, then points it at the link', async () => {
    const tab = { opener: {}, location: { href: '' }, close: () => {} }
    const open = vi.spyOn(globalThis, 'open').mockReturnValue(tab as unknown as Window)
    const asked: boolean[] = []
    await openDownload('plan.pdf', async inline => {
      asked.push(inline)
      return { url: 'https://files.test/x' }
    })
    expect(open).toHaveBeenCalledWith('', '_blank')
    expect(asked).toEqual([true])
    expect(tab.location.href).toBe('https://files.test/x')
    expect(tab.opener).toBeNull()
    open.mockRestore()
  })

  it('opens no tab for a file that downloads, and closes it when the link fails', async () => {
    const open = vi.spyOn(globalThis, 'open')
    const asked: boolean[] = []
    // jsdom can't navigate: a failing link keeps the test off `location.assign`
    await expect(openDownload('sheet.xlsx', async inline => {
      asked.push(inline)
      throw new Error('offline')
    })).rejects.toThrow('offline')
    expect(open).not.toHaveBeenCalled()
    expect(asked).toEqual([false])

    const close = vi.fn()
    open.mockReturnValue({ close } as unknown as Window)
    await expect(openDownload('plan.pdf', async () => {
      throw new Error('offline')
    })).rejects.toThrow('offline')
    expect(close).toHaveBeenCalled()
    open.mockRestore()
  })
})
