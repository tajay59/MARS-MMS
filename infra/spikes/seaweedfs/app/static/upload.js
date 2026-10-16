const MiB = 1024 * 1024
const log = document.querySelector('#log')

function line (text, cls) {
  const span = document.createElement('span')
  if (cls) span.className = cls
  span.textContent = text + '\n'
  log.append(span)
}
const pass = text => line('PASS  ' + text, 'pass')
const fail = text => line('FAIL  ' + text, 'fail')

async function api (method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(`${path}: ${data.error}`)
  return data
}

// One part, straight to the files host. A missing ETag means CORS doesn't expose it.
async function putPart (part, blob) {
  let res
  try {
    res = await fetch(part.url, { method: 'PUT', body: blob })
  } catch (error) {
    throw new Error(`part ${part.part_number}: request blocked (CORS preflight refused?): ${error.message}`)
  }
  if (!res.ok) throw new Error(`part ${part.part_number}: HTTP ${res.status} ${await res.text()}`)
  const etag = res.headers.get('ETag')
  if (!etag) throw new Error(`part ${part.part_number}: ETag not readable. The files host must expose ETag (CORS)`)
  return { part_number: part.part_number, etag }
}

async function upload (file) {
  log.textContent = ''
  line(`Uploading ${file.name} (${(file.size / MiB).toFixed(1)} MiB)`)
  const started = performance.now()
  try {
    const session = await api('POST', '/api/uploads', {
      filename: file.name, size: file.size, content_type: file.type,
    })
    line(`Upload ${session.upload_id.slice(0, 12)}…: ${session.parts.length} part(s)`)
    const done = []
    for (const part of session.parts) {
      const start = (part.part_number - 1) * session.part_size
      done.push(await putPart(part, file.slice(start, start + session.part_size)))
      line(`  part ${part.part_number}/${session.parts.length} ETag ${done.at(-1).etag}`)
    }
    pass(`All parts uploaded cross-origin with readable ETags`)

    const result = await api('POST', '/api/uploads/complete', {
      key: session.key, upload_id: session.upload_id, parts: done,
    })
    if (result.size === file.size) pass(`Completed: stored size ${result.size} bytes matches`)
    else fail(`Completed, but stored size ${result.size} != ${file.size}`)

    const download = await fetch(result.download_url)
    const blob = await download.blob()
    if (download.ok && blob.size === file.size) pass(`Presigned GET read back ${blob.size} bytes cross-origin`)
    else fail(`Presigned GET: HTTP ${download.status}, ${blob.size} bytes`)

    line(`Took ${((performance.now() - started) / 1000).toFixed(1)} s`)
  } catch (error) {
    fail(error.message)
  }
}

document.querySelector('#upload').addEventListener('click', () => {
  const file = document.querySelector('#file').files[0]
  if (file) upload(file)
  else line('Choose a file first, or use the generated file.')
})

document.querySelector('#generated').addEventListener('click', () => {
  const bytes = new Uint8Array(20 * MiB)
  for (let i = 0; i < bytes.length; i += 4096) bytes[i] = i % 251
  upload(new File([bytes], 'generated-20MiB.bin', { type: 'application/octet-stream' }))
})

document.querySelector('#abandon').addEventListener('click', async () => {
  try {
    const session = await api('POST', '/api/uploads', { filename: 'abandoned.bin', size: 10 * MiB })
    await putPart(session.parts[0], new Blob([new Uint8Array(8 * MiB)]))
    pass(`Started ${session.key} and uploaded part 1 of 2; not completing it`)
    await listOpen()
  } catch (error) {
    fail(error.message)
  }
})

async function listOpen () {
  const { uploads } = await api('GET', '/api/uploads/open')
  const table = document.querySelector('#open')
  const body = table.querySelector('tbody')
  body.replaceChildren()
  for (const u of uploads) {
    const row = body.insertRow()
    row.insertCell().textContent = u.key
    row.insertCell().textContent = new Date(u.initiated).toLocaleString()
    const button = document.createElement('button')
    button.textContent = 'Abort'
    button.addEventListener('click', async () => {
      await api('POST', '/api/uploads/abort', { key: u.key, upload_id: u.upload_id })
      pass(`Aborted ${u.key}`)
      await listOpen()
    })
    row.insertCell().append(button)
  }
  table.hidden = uploads.length === 0
  line(`${uploads.length} open upload(s)`)
}

document.querySelector('#list').addEventListener('click', () => listOpen().catch(error => fail(error.message)))
