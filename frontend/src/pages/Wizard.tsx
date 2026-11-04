import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, CheckCircle2, Equal, FileSpreadsheet, Loader2, Minus, Plus, Rocket, Shuffle, Square, TrendingUp, UploadCloud, Users } from 'lucide-react'
import type { Ctx } from '../App'
import type { Feature } from '../types'
import { ErrorView } from '../components/ui'
import { api } from '../services/api'

type Role = 'skill' | 'match' | 'mix'
interface Pick { role?: Role; importance: number }
interface Col { name: string; suggested_type: Feature['type']; unique: number; missing: number }

const ROLES = [
  { id: 'skill' as Role, label: 'Skill', hint: 'Higher is better for a person', ex: 'e.g. test score, years of experience', icon: TrendingUp },
  { id: 'match' as Role, label: 'Match', hint: 'Put similar people together', ex: 'e.g. communication level, availability', icon: Equal },
  { id: 'mix' as Role, label: 'Mix', hint: 'Put different people together', ex: 'e.g. department, specialty', icon: Shuffle },
]
const IMPORTANCE = ['', 'Nice to have', 'Minor', 'Important', 'Very important', 'Critical']
const TYPE_LABEL: Record<string, string> = { numeric_continuous: 'number', numeric_integer: 'whole number', categorical: 'category', binary: 'yes / no' }

const toFeature = (c: Col, p: Pick): Feature => ({
  name: c.name, column: c.name, type: c.suggested_type, importance: p.importance, required: true,
  role: p.role === 'skill' ? 'value' : 'compat', compat_method: p.role === 'mix' ? 'complementarity' : 'similarity',
  direction: 'higher_better', min: null, max: null, categories: null, category_values: null, compat_matrix: null, missing_policy: 'error', fill_value: null })

const choiceCls = (sel: boolean, off = false) =>
  `flex w-full items-start gap-3 rounded-xl border-2 p-4 text-left transition focus:outline-none focus:ring-2 focus:ring-indigo-400 ${off ? 'cursor-not-allowed opacity-40' : 'hover:-translate-y-0.5 hover:shadow-md'} ${sel ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/60' : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'}`

export default function Wizard({ ctx }: { ctx: Ctx }) {
  const [step, setStep] = useState(0)
  const [cols, setCols] = useState<Col[]>([])
  const [rows, setRows] = useState<any[]>([])
  const [n, setN] = useState(0)
  const [idCol, setIdCol] = useState<string | null>(null)       // null = not answered yet, '' = none
  const [chosenNames, setChosenNames] = useState<string[]>([])
  const [picks, setPicks] = useState<Record<string, Pick>>({})
  const [size, setSize] = useState(3)
  const [everyone, setEveryone] = useState<boolean | null>(null)
  const [err, setErr] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const timer = useRef<number | null>(null)
  const head = useRef<HTMLHeadingElement>(null)
  useEffect(() => () => { if (timer.current) clearInterval(timer.current) }, [])
  useEffect(() => { head.current?.focus() }, [step])

  const chosen = cols.filter(c => chosenNames.includes(c.name))
  const steps = ['upload', 'id', 'columns', ...chosen.map(c => 'col:' + c.name), 'size', 'everyone', 'review']
  const cur = steps[step]
  const total = steps.length

  async function onFile(f?: File) {
    if (!f) return
    setErr(null)
    try {
      const d = await api.preview(f)
      setCols(d.columns); setRows(d.preview); setN(d.n_rows); setIdCol(null); setChosenNames([]); setPicks({})
      ctx.set({ file: f, result: null })
    } catch (e) { setErr(e); setCols([]) }
  }
  const examples = (name: string) => rows.slice(0, 3).map(r => r[name]).join(', ')
  const setPick = (name: string, patch: Partial<Pick>) => setPicks(p => ({ ...p, [name]: { ...(p[name] ?? { importance: 3 }), ...patch } }))
  const toggleCol = (name: string) => setChosenNames(l => (l.includes(name) ? l.filter(x => x !== name) : [...l, name]))

  const canNext = useMemo(() => {
    if (cur === 'upload') return cols.length > 0
    if (cur === 'id') return idCol !== null
    if (cur === 'columns') return chosen.length > 0
    if (cur?.startsWith('col:')) return !!picks[cur.slice(4)]?.role
    if (cur === 'size') return n >= size
    if (cur === 'everyone') return everyone !== null
    return false
  }, [cur, cols, idCol, chosen.length, picks, n, size, everyone])

  const summary = useMemo(() => {
    if (!n) return ''
    if (everyone === false) return `${n} people → ${Math.floor(n / size)} teams of ${size}, ${n % size} left out`
    const lo = Math.ceil(n / (size + 1)), hi = Math.floor(n / size)
    return lo <= hi ? `${n} people → ${lo === hi ? lo : `${lo}–${hi}`} teams of ${size}–${size + 1}, nobody left out` : `${n} people can't all fit into teams of ${size}–${size + 1}`
  }, [n, size, everyone])

  async function run() {
    if (!ctx.file) return
    setErr(null); setBusy(true)
    const features = chosen.map(c => toFeature(c, picks[c.name]))
    const team = everyone
      ? { policy: 'full_coverage', preferred_size: size, min_size: size, max_size: size + 1, strict_team_count: true, strict_team_size: false, full_coverage: true, equal_sizes: false, priority: 'coverage_first' }
      : { policy: 'leave_unassigned', preferred_size: size, strict_team_count: true, strict_team_size: true, full_coverage: false, equal_sizes: true, priority: 'coverage_first' }
    const settings = { objective: { alpha: 1, beta: 1, edge_mode: 'soft' as const, threshold: 0.5 }, team,
      limits: { time_limit: 20, node_limit: null, max_cliques: 250000 } }
    const idc = idCol ?? ''
    try {
      const v = await api.validate(ctx.file, features, idc)
      if (!v.report.ok) { setErr({ message: 'Fix these problems in your CSV first:', details: v.report }); setBusy(false); return }
      const { task_id } = await api.optimize(ctx.file, features, idc, settings)
      ctx.set({ taskId: task_id, result: null })
      timer.current = window.setInterval(async () => {
        try {
          const s = await api.status(task_id)
          if (!['queued', 'running'].includes(s.status)) {
            clearInterval(timer.current!); setBusy(false)
            if (s.status !== 'failed') { const r = await api.results(task_id); ctx.set({ taskId: task_id, result: r.result }); ctx.go('results') }
            else setErr({ message: s.error?.message ?? 'Something went wrong while finding teams.' })
          }
        } catch (e) { clearInterval(timer.current!); setErr(e); setBusy(false) }
      }, 500)
    } catch (e) { setErr(e); setBusy(false) }
  }

  const title = (t: string, sub?: string) => (
    <div className="mb-5">
      <h1 ref={head} tabIndex={-1} className="text-2xl font-bold outline-none md:text-3xl">{t}</h1>
      {sub && <p className="mt-1 text-sm text-slate-600">{sub}</p>}
    </div>)
  const colName = cur?.startsWith('col:') ? cur.slice(4) : ''
  const col = cols.find(c => c.name === colName)

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-4">
        <div className="mb-1 flex justify-between text-xs text-slate-500"><span>Step {step + 1} of {total}</span><span>{Math.round(((step + 1) / total) * 100)}%</span></div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuemin={1} aria-valuemax={total} aria-valuenow={step + 1}>
          <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all duration-500" style={{ width: `${((step + 1) / total) * 100}%` }} /></div>
      </div>

      <section key={cur} className="card step-in p-6" aria-live="polite">
        {cur === 'upload' && <>
          {title('Upload your CSV', 'One row per person, one column per detail (score, department, …).')}
          <label onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files[0]) }}
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-10 text-center transition focus-within:ring-2 focus-within:ring-indigo-400 ${drag ? 'scale-[1.02] border-indigo-500 bg-indigo-50 dark:bg-indigo-950/60' : 'border-slate-300 hover:border-indigo-400 dark:border-slate-600'}`}>
            {cols.length ? <FileSpreadsheet className="text-emerald-500" size={40} /> : <UploadCloud className="text-indigo-500" size={40} />}
            <span className="font-medium">{cols.length && ctx.file ? `${ctx.file.name} · ${n} people · ${cols.length} columns` : 'Drop a .csv file here, or click to browse'}</span>
            {cols.length > 0 && <span className="text-xs text-slate-500">Click to choose a different file</span>}
            <input type="file" accept=".csv,text/csv" className="sr-only" aria-label="CSV file" onChange={e => onFile(e.target.files?.[0])} />
          </label>
          <div className="mt-3"><ErrorView err={err} /></div></>}

        {cur === 'id' && <>
          {title('Who is each row?', 'Pick the column with names or IDs so results are easy to read.')}
          <div className="space-y-2" role="radiogroup" aria-label="ID column">
            {cols.map(c => <button key={c.name} role="radio" aria-checked={idCol === c.name} className={choiceCls(idCol === c.name)} onClick={() => setIdCol(c.name)}>
              <div><div className="font-semibold">{c.name}</div><div className="text-xs text-slate-500">e.g. {examples(c.name)}</div></div></button>)}
            <button role="radio" aria-checked={idCol === ''} className={choiceCls(idCol === '')} onClick={() => setIdCol('')}>
              <div><div className="font-semibold">None of these</div><div className="text-xs text-slate-500">Rows will be called row-1, row-2, …</div></div></button>
          </div></>}

        {cur === 'columns' && <>
          {title('Which columns should decide the teams?', 'Tick every column that matters. Skip the ones that don’t.')}
          <div className="space-y-2">
            {cols.filter(c => c.name !== idCol).map(c => { const on = chosenNames.includes(c.name); return (
              <button key={c.name} role="checkbox" aria-checked={on} className={choiceCls(on)} onClick={() => toggleCol(c.name)}>
                <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border ${on ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-slate-400'}`}>{on && <CheckCircle2 size={14} />}</span>
                <div className="min-w-0"><div className="font-semibold">{c.name} <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal text-slate-600 dark:bg-slate-800 dark:text-slate-300">{TYPE_LABEL[c.suggested_type]}</span>
                  {c.missing > 0 && <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-normal text-red-700 dark:bg-red-950 dark:text-red-300">{c.missing} missing</span>}</div>
                  <div className="truncate text-xs text-slate-500">e.g. {examples(c.name)}</div></div></button>) })}
          </div></>}

        {col && <>
          {title(`What does “${col.name}” mean?`, `Examples: ${examples(col.name)}`)}
          <div className="space-y-2" role="radiogroup" aria-label={`Role of ${col.name}`}>
            {ROLES.map(r => { const off = r.id === 'skill' && col.suggested_type === 'categorical'; const sel = picks[col.name]?.role === r.id; return (
              <button key={r.id} role="radio" aria-checked={sel} disabled={off} className={choiceCls(sel, off)} onClick={() => setPick(col.name, { role: r.id })}>
                <r.icon className="mt-0.5 shrink-0 text-indigo-500" size={22} />
                <div><div className="font-semibold">{r.label} — {r.hint}</div><div className="text-xs text-slate-500">{off ? 'Not available for categories (use Match or Mix)' : r.ex}</div></div></button>) })}
          </div>
          <div className="mt-5"><div className="flex justify-between text-sm"><span className="font-medium">How important is it?</span><b className="text-indigo-600 dark:text-indigo-300">{IMPORTANCE[picks[col.name]?.importance ?? 3]}</b></div>
            <input type="range" min={1} max={5} step={1} className="mt-2 w-full accent-indigo-600" aria-label={`Importance of ${col.name}`} value={picks[col.name]?.importance ?? 3} onChange={e => setPick(col.name, { importance: Number(e.target.value) })} />
            <div className="flex justify-between text-xs text-slate-500"><span>Nice to have</span><span>Critical</span></div></div></>}

        {cur === 'size' && <>
          {title('How many people per team?')}
          <div className="flex items-center justify-center gap-6 py-4">
            <button className="rounded-full border-2 border-slate-300 p-3 transition hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800" onClick={() => setSize(s => Math.max(2, s - 1))} aria-label="Smaller teams"><Minus /></button>
            <div className="w-24 text-center text-6xl font-extrabold text-indigo-600 dark:text-indigo-300" aria-live="polite">{size}</div>
            <button className="rounded-full border-2 border-slate-300 p-3 transition hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800" onClick={() => setSize(s => Math.min(10, s + 1))} aria-label="Larger teams"><Plus /></button></div>
          <p className="text-center text-sm text-slate-600">{n >= size ? `You have ${n} people.` : `You only have ${n} people — pick a smaller size.`}</p></>}

        {cur === 'everyone' && <>
          {title('Must everyone be in a team?')}
          <div className="space-y-2" role="radiogroup" aria-label="Everyone in a team">
            <button role="radio" aria-checked={everyone === true} className={choiceCls(everyone === true)} onClick={() => setEveryone(true)}><div><div className="font-semibold">Yes, include everyone</div><div className="text-xs text-slate-500">Team sizes may differ by one ({size} or {size + 1}).</div></div></button>
            <button role="radio" aria-checked={everyone === false} className={choiceCls(everyone === false)} onClick={() => setEveryone(false)}><div><div className="font-semibold">No, leave extras out</div><div className="text-xs text-slate-500">All teams exactly {size} people; leftovers are listed.</div></div></button>
          </div>
          {everyone !== null && <div className="mt-4 rounded-lg bg-indigo-50 p-3 text-sm text-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-200">{summary}</div>}</>}

        {cur === 'review' && <>
          {title('Ready to find your teams', 'Check your answers, then start.')}
          <dl className="grid grid-cols-3 gap-y-2 text-sm">
            <dt className="text-slate-500">File</dt><dd className="col-span-2 font-medium">{ctx.file?.name} ({n} people)</dd>
            <dt className="text-slate-500">Row labels</dt><dd className="col-span-2 font-medium">{idCol || 'row numbers'}</dd>
            <dt className="text-slate-500">Columns</dt><dd className="col-span-2 font-medium">{chosen.map(c => `${c.name} (${picks[c.name].role}, ${IMPORTANCE[picks[c.name].importance]})`).join(' · ')}</dd>
            <dt className="text-slate-500">Teams</dt><dd className="col-span-2 font-medium">{summary}</dd></dl>
          <button className="btn mt-5 px-6 py-3 text-base" disabled={busy} onClick={run}>{busy ? <><Loader2 className="animate-spin" size={18} />Finding teams…</> : <><Rocket size={18} />Find teams</>}</button>
          {busy && <div className="mt-4 space-y-2">
            <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"><div className="h-full w-1/3 animate-pulse rounded-full bg-indigo-500" /></div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600"><span>This can take up to 20 seconds.</span>
              <button className="btn-ghost" onClick={() => ctx.taskId && api.cancel(ctx.taskId)}><Square size={14} />Stop and show the best so far</button></div></div>}
          <div className="mt-3"><ErrorView err={err} /></div>
          </>}
      </section>

      <div className="mt-4 flex items-center justify-between">
        <button className="btn-ghost" disabled={step === 0 || busy} onClick={() => setStep(s => s - 1)}><ArrowLeft size={16} />Back</button>
        {cur !== 'review' && <button className="btn px-5" disabled={!canNext} onClick={() => setStep(s => s + 1)}>Next<ArrowRight size={16} /></button>}
      </div>
      {!canNext && cur !== 'review' && <p className="mt-2 text-right text-xs text-slate-500">
        {cur === 'upload' ? 'Choose a CSV to continue.' : cur === 'columns' ? 'Tick at least one column.' : cur === 'size' ? 'Pick a team size that fits your data.' : 'Choose an option to continue.'}</p>}
      <p className="mt-6 flex items-center justify-center gap-1 text-xs text-slate-400"><Users size={12} />CliqueCraft</p>
    </div>
  )
}
