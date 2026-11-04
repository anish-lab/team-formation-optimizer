import { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import type { ApiErr } from '../types'

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
