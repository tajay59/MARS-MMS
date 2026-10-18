import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

/*
  Seeds the TP users (mms_common.testing.seed) into the running stack, as infra/tests does.
  Skipped against a remote host (MMS_E2E_URL), where the seed users must already exist.
*/
export default function globalSetup (): void {
  if (process.env.MMS_E2E_URL) {
    return
  }
  const infra = path.resolve(import.meta.dirname, '../../infra')
  const password = seedPassword(infra)
  process.env.MMS_SEED_PASSWORD = password
  const docker = process.platform === 'win32' && process.env.LOCALAPPDATA
    ? path.join(process.env.LOCALAPPDATA, 'Programs', 'DockerDesktop', 'resources', 'bin', 'docker.exe')
    : 'docker'
  const exec = (args: string[]) => execFileSync(
    existsSync(docker) ? docker : 'docker',
    ['compose', '-f', 'compose.yml', '-f', 'compose.dev.yml', 'exec', '-T', ...args],
    { cwd: infra, stdio: 'inherit', env: { ...process.env, MSYS_NO_PATHCONV: '1' } },
  )
  exec(['-e', `AUTH_SEED_PASSWORD=${password}`, 'auth', 'python', '-m', 'app.cli', 'seed'])
  // The demo stations (made up), after auth's organizations; existing codes are skipped
  exec(['operations', 'python', '-m', 'app.cli', 'seed'])
}

function seedPassword (infra: string): string {
  if (process.env.MMS_SEED_PASSWORD) {
    return process.env.MMS_SEED_PASSWORD
  }
  const env = readFileSync(path.join(infra, '.env'), 'utf8')
  const line = env.split(/\r?\n/).find(l => l.startsWith('AUTH_SEED_PASSWORD='))
  if (!line) {
    throw new Error('AUTH_SEED_PASSWORD is not in infra/.env')
  }
  return line.slice('AUTH_SEED_PASSWORD='.length).trim()
}
