import { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import type { ApiErr } from '../types'

export const Card = ({ title, children, right }: { title?: string; children: ReactNode; right?: ReactNode }) => (
  <section className="card">
    {(title || right) && <div className="mb-3 flex items-center justify-between"><h2 className="text-base font-semibold">{title}</h2>{right}</div>}
    {children}
  </section>
)
export const Field = ({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) => (
  <label className="block"><span className="lbl">{label}</span>{children}{hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}</label>
)
export const Stat = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-semibold">{value}</div></div>
)
export const Notice = ({ kind = 'info', children }: { kind?: 'info' | 'warn' | 'ok' | 'err'; children: ReactNode }) => {
  const m = { info: ['bg-sky-50 text-sky-900 border-sky-200', Info], warn: ['bg-amber-50 text-amber-900 border-amber-200', AlertTriangle],
    ok: ['bg-emerald-50 text-emerald-900 border-emerald-200', CheckCircle2], err: ['bg-red-50 text-red-900 border-red-200', AlertTriangle] }[kind] as any
  const Icon = m[1]
  return <div className={`flex gap-2 rounded-lg border p-3 text-sm ${m[0]}`}><Icon size={16} className="mt-0.5 shrink-0" /><div>{children}</div></div>
}
export function ErrorView({ err }: { err: ApiErr | null }) {
  if (!err) return null
  const d = err.details
  return (
    <Notice kind="err">
      <div className="font-medium">{err.message ?? 'Request failed'}</div>
      {Array.isArray(d) && d.map((x, i) => typeof x === 'string' ? <div key={i}>• {x}</div> :
        <div key={i}>• {x.message}{x.suggestions?.length ? <ul className="ml-4 list-disc text-xs">{x.suggestions.map((s: string) => <li key={s}>{s}</li>)}</ul> : null}</div>)}
      {d?.errors && <ul className="mt-1 max-h-40 overflow-auto text-xs">{d.errors.slice(0, 30).map((e: any, i: number) =>
        <li key={i}>row {e.row ?? '–'} · {e.column ?? '–'} · {e.message}</li>)}</ul>}
    </Notice>
  )
}
export const fmt = (x: number | null | undefined, d = 3) => (x === null || x === undefined ? '–' : Number(x).toFixed(d))
