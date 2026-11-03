import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Ctx } from '../App'
import { Card, Notice, Stat, fmt } from '../components/ui'

const COLORS = ['#4f46e5', '#059669', '#d97706', '#db2777', '#0891b2', '#7c3aed', '#65a30d', '#dc2626', '#0d9488', '#9333ea']

export default function ResultsPage({ ctx }: { ctx: Ctx }) {
  const r = ctx.result
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [q, setQ] = useState('')
  if (!r) return <Notice>No result yet. Run an optimization first.</Notice>
  const s = r.summary, st = r.stats
  const guarantee = r.optimality_proven ? 'Proven optimum' : r.teams.length ? 'Best found, not proven' : r.status
  const teams = r.teams.filter((t: any) => !q || t.members.some((m: any) => m.id.toLowerCase().includes(q.toLowerCase())))
  return (
    <>
      <Notice kind={r.optimality_proven ? 'ok' : 'warn'}><b>{guarantee}</b> · status {r.status} · termination: {r.termination_reason}</Notice>
      {r.issues?.map((i: any, k: number) => <Notice key={k} kind="warn"><div>{i.message}</div>{i.suggestions?.length > 0 && <ul className="ml-4 list-disc text-xs">{i.suggestions.map((x: string) => <li key={x}>{x}</li>)}</ul>}</Notice>)}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Teams" value={s.teams} /><Stat label="Assigned" value={s.assigned} /><Stat label="Unassigned" value={s.unassigned} /><Stat label="Total score" value={fmt(s.total_score, 4)} />
        <Stat label="Value part" value={fmt(s.value_contribution, 4)} /><Stat label="Compatibility part" value={fmt(s.compat_contribution, 4)} />
        <Stat label="Runtime (s)" value={fmt(s.runtime_s, 3)} /><Stat label="Team sizes" value={s.team_sizes.join(', ') || '–'} />
        <Stat label="Nodes explored" value={st.nodes} /><Stat label="Pruned by bound" value={st.pruned_by_bound} /><Stat label="Pruned by feasibility" value={st.pruned_by_feasibility} /><Stat label="Incumbent updates" value={st.incumbent_updates} /></div>
      <Card title="Objective used">
        {st.algorithm === 'bbmcw_team_graph' && <p className="text-xs">Solved with AMTS and BBMCW (San Segundo, Furini &amp; Artieda, 2019) as a maximum weighted clique on a graph of {st.team_graph_vertices} possible teams, where two teams are connected if they share no one.</p>}
        <p className="text-xs">{r.objective.formula}</p>
        <p className="text-xs text-slate-600">α={r.objective.alpha}, β={r.objective.beta}, edges: {r.objective.edge_mode} (threshold {r.objective.threshold}), k = {r.objective.preferred_size}. Priority: {r.objective.priority_explained}.</p>
        <p className="text-xs text-slate-600">Constraints: sizes {r.constraints.min_size}–{r.constraints.max_size}, teams {r.constraints.teams_min}–{r.constraints.teams_max}, full coverage: {String(r.constraints.full_coverage)}, equal sizes: {String(r.constraints.equal_sizes)}.</p>
        {r.warnings?.map((w: string) => <p key={w} className="text-xs text-amber-700">⚠ {w}</p>)}
      </Card>
      <Card title="Teams" right={<input className="inp w-48" placeholder="Filter by candidate ID" value={q} onChange={e => setQ(e.target.value)} aria-label="Filter teams" />}>
        <div className="grid gap-3 md:grid-cols-2">{teams.map((t: any) => { const col = COLORS[(t.team - 1) % COLORS.length]; return (
          <div key={t.team} className="overflow-hidden rounded-xl border shadow-sm transition hover:shadow-md">
            <button className="flex w-full items-center justify-between px-3 py-2 text-left text-white" style={{ background: col }} onClick={() => setOpen({ ...open, [t.team]: !open[t.team] })} aria-expanded={!!open[t.team]}>
              <span className="flex items-center gap-2 text-sm font-semibold">{open[t.team] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}Team {t.team}</span>
              <span className="text-xs">{t.size} members · score {fmt(t.score, 3)}</span></button>
            <div className="flex flex-wrap gap-1 p-3">{t.members.map((m: any) => <span key={m.id} className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: col + '22', color: col }}>{m.id}</span>)}
              {!t.satisfies_hard_constraints && <span className="text-xs text-red-600">violates constraints</span>}</div>
            {open[t.team] && <div className="space-y-2 border-t p-3 text-xs">
              <div>Value part {fmt(t.value_score, 4)} · compatibility part {fmt(t.compat_score, 4)} · mean pairwise compatibility {fmt(t.mean_pair_compat)}</div>
              <table className="w-full"><thead><tr><th className="text-left">Feature</th><th className="text-left">Role</th><th className="text-left">Mean value</th><th className="text-left">Mean pair score</th></tr></thead>
                <tbody>{t.feature_contributions.map((f: any) => <tr key={f.feature} className="border-t"><td>{f.feature}</td><td>{f.role}</td><td>{fmt(f.mean_value_score)}</td><td>{fmt(f.mean_pair_score)}</td></tr>)}</tbody></table></div>}
          </div>) })}{teams.length === 0 && <p className="text-sm text-slate-500">No teams to show.</p>}</div>
      </Card>
      <Card title={`Unassigned candidates (${r.unassigned.length})`}>
        {r.unassigned.length === 0 ? <p className="text-sm text-slate-500">Everyone was assigned.</p> :
          <table className="w-full text-xs"><thead><tr><th className="text-left">ID</th><th className="text-left">Compatible candidates</th><th className="text-left">Reason</th></tr></thead>
            <tbody>{r.unassigned.map((u: any) => <tr key={u.id} className="border-t"><td>{u.id}</td><td>{u.compatible_candidates}</td><td>{u.reason}</td></tr>)}</tbody></table>}
      </Card>
    </>
  )
}
