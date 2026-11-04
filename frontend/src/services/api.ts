import type { Feature, Settings, ApiErr } from '../types'

async function handle(r: Response) {
  const d = await r.json().catch(() => ({}))
  if (!r.ok || d.ok === false) throw (d.error ?? { message: r.statusText }) as ApiErr
  return d
}
function fd(file: File, features?: Feature[], idColumn?: string, settings?: Settings) {
  const f = new FormData()
  f.append('file', file)
  if (features) f.append('schema', JSON.stringify(features.map(toWire)))
  f.append('id_column', idColumn ?? '')
  if (settings) f.append('settings', JSON.stringify(cleanSettings(settings)))
  return f
}
const toWire = (f: Feature) => ({ ...f, fill_value: f.fill_value || null })
const dropEmpty = (o: object) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== '' && v !== undefined))
const cleanSettings = (s: Settings) => ({ ...s, team: dropEmpty(s.team), limits: dropEmpty(s.limits) })
const post = (u: string, body: BodyInit) => fetch('/api' + u, { method: 'POST', body }).then(handle)

export const api = {
  preview: (file: File) => post('/preview-data', fd(file)),
  validate: (file: File, features: Feature[], idc: string) => post('/validate-csv', fd(file, features, idc)),
  optimize: (file: File, features: Feature[], idc: string, s: Settings) => post('/optimize', fd(file, features, idc, s)),
  status: (id: string) => fetch(`/api/optimization/${id}`).then(handle),
  results: (id: string) => fetch(`/api/optimization/${id}/results`).then(handle),
  cancel: (id: string) => fetch(`/api/optimization/${id}/cancel`, { method: 'POST' }).then(handle),
}
