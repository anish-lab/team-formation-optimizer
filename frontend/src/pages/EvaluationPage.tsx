import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Tooltip, XAxis, YAxis } from 'recharts'
import type { Ctx } from '../App'
import { Card, ErrorView, Notice, fmt } from '../components/ui'
import { api } from '../services/api'

const GUARANTEE: Record<string, string> = { proven_optimum: 'proven optimum', best_before_limit: 'best before limit', heuristic: 'heuristic', infeasible: 'infeasible' }

export default function EvaluationPage({ ctx }: { ctx: Ctx }) {
  const [ev, setEv] = useState<any>(null)
  const [err, setErr] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [reps, setReps] = useState(3)
  async function run() {
    if (!ctx.file) return
    setBusy(true); setErr(null)
    try { setEv((await api.evaluate(ctx.file, ctx.features, ctx.idColumn, ctx.settings, reps)).evaluation) } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const label = (r: any) => `${r.algorithm}${r.coloring === true ? ' (coloring on)' : r.coloring === false ? ' (coloring off)' : ''}`
  const data = ev?.rows.map((r: any) => ({ name: label(r), nodes: r.nodes ?? 0, pruned: r.pruned_by_bound ?? 0, runtime: r.runtime_s.mean })) ?? []
  return (
    <>
      <Card title="Algorithm evaluation (measured on your data and current settings)" right={<div className="flex items-center gap-2"><label className="text-xs">repeats <input className="inp inline w-16" type="number" min={1} max={5} value={reps} onChange={e => setReps(Number(e.target.value))} /></label>
        <button className="btn" disabled={!ctx.validated || busy} onClick={run}>{busy ? 'Running…' : 'Run evaluation'}</button></div>}>
        {!ctx.validated && <Notice kind="warn">Validate your data first.</Notice>}
        <ErrorView err={err} />
        {ev && <div className="space-y-3">
          <p className="text-xs text-slate-600">Graph: {ev.graph.vertices} vertices · {ev.graph.edges} edges · density {fmt(ev.graph.density)}.</p>
          <div className="overflow-auto"><table className="w-full text-xs"><thead><tr className="text-left"><th>Algorithm</th><th>Guarantee</th><th>Runtime (s, mean)</th><th>Nodes</th><th>Pruned (bound)</th><th>Pruned (feas.)</th><th>Pruning eff.</th><th>Objective</th><th>Teams</th><th>Assigned</th><th>Sizes</th><th>Feasible</th></tr></thead>
            <tbody>{ev.rows.map((r: any, i: number) => <tr key={i} className="border-t"><td>{label(r)}</td><td>{GUARANTEE[r.guarantee] ?? r.guarantee}</td><td>{fmt(r.runtime_s.mean, 4)}</td><td>{r.nodes ?? '–'}</td><td>{r.pruned_by_bound ?? '–'}</td><td>{r.pruned_by_feasibility ?? '–'}</td><td>{r.pruning_efficiency !== undefined ? fmt(r.pruning_efficiency) : '–'}</td><td>{fmt(r.objective, 4)}</td><td>{r.teams}</td><td>{r.coverage}</td><td>{r.team_sizes.join(',')}</td><td>{String(r.feasible)}</td></tr>)}</tbody></table></div>
          <BarChart width={760} height={280} data={data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} angle={-15} height={70} textAnchor="end" /><YAxis /><Tooltip /><Legend />
            <Bar dataKey="nodes" fill="#4f46e5" name="nodes explored" /><Bar dataKey="pruned" fill="#059669" name="pruned by bound" /></BarChart>
          {ev.vertex_weighted && <div className="space-y-1">
            <h3 className="text-sm font-semibold">Classical vertex-weighted problem: paper-style algorithm vs this project’s adapted solver</h3>
            <p className="text-xs text-slate-600">{ev.vertex_weighted.note}</p>
            <div className="overflow-auto"><table className="w-full text-xs"><thead><tr className="text-left"><th>Algorithm</th><th>Guarantee</th><th>Runtime (s, mean)</th><th>Nodes</th><th>Vertices pruned / branches pruned</th><th>Best weight</th><th>Clique size</th></tr></thead>
              <tbody>{ev.vertex_weighted.rows.map((r: any) => <tr key={r.algorithm} className="border-t"><td>{r.algorithm}</td><td>{GUARANTEE[r.guarantee] ?? r.guarantee}</td><td>{fmt(r.runtime_s.mean, 4)}</td><td>{r.nodes}</td><td>{r.pruned_by_bound}</td><td>{fmt(r.objective, 4)}</td><td>{r.clique_size}</td></tr>)}</tbody></table></div></div>}
          {ev.notes.map((n: string) => <Notice key={n}>{n}</Notice>)}</div>}
      </Card>
    </>
  )
}
