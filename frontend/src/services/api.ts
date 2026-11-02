import type { Feature, Settings, ApiErr } from '../types'

async function handle(r: Response) {
  const d = await r.json().catch(() => ({}))
  if (!r.ok || d.ok === false) throw (d.error ?? { message: r.statusText }) as ApiErr
  return d
}
function fd(file: File, features?: Feature[], idColumn?: string, settings?: Settings, extra: Record<string, string> = {}) {
  const f = new FormData()
  f.append('file', file)
  if (features) f.append('schema', JSON.stringify(features.map(toWire)))
  f.append('id_column', idColumn ?? '')
  if (settings) f.append('settings', JSON.stringify(cleanSettings(settings)))
  Object.entries(extra).forEach(([k, v]) => f.append(k, v))
  return f
}
const toWire = (f: Feature) => ({ ...f, fill_value: f.fill_value || null })
const dropEmpty = (o: object) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== '' && v !== undefined))
const cleanSettings = (s: Settings) => ({ ...s, team: dropEmpty(s.team), limits: dropEmpty(s.limits) })
const post = (u: string, body: BodyInit) => fetch('/api' + u, { method: 'POST', body }).then(handle)

export const api = {
  preview: (file: File) => post('/preview-data', fd(file)),
  validate: (file: File, features: Feature[], idc: string) => post('/validate-csv', fd(file, features, idc)),
  checkConfig: (n: number, team: Settings['team']) =>
    fetch('/api/validate-configuration', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ n_candidates: n, team: Object.fromEntries(Object.entries(team).filter(([, v]) => v !== null && v !== '' && v !== undefined)) }) }).then(handle),
  buildGraph: (file: File, features: Feature[], idc: string, s: Settings) => post('/build-graph', fd(file, features, idc, s)),
  optimize: (file: File, features: Feature[], idc: string, s: Settings) => post('/optimize', fd(file, features, idc, s)),
  evaluate: (file: File, features: Feature[], idc: string, s: Settings, repeats: number) =>
    post('/evaluate', fd(file, features, idc, s, { repeats: String(repeats) })),
  status: (id: string) => fetch(`/api/optimization/${id}`).then(handle),
  results: (id: string) => fetch(`/api/optimization/${id}/results`).then(handle),
  cancel: (id: string) => fetch(`/api/optimization/${id}/cancel`, { method: 'POST' }).then(handle),
  exportUrl: (id: string, format: string) => `/api/optimization/${id}/export?format=${format}`,
}
