import type { Ctx } from '../App'
import { Notice } from '../components/ui'

const COLORS = ['#4f46e5', '#059669', '#d97706', '#db2777', '#0891b2', '#7c3aed', '#65a30d', '#dc2626', '#0d9488', '#9333ea']
const NO_TEAMS: Record<string, string> = {
  too_large: 'There are too many possible teams to search. Try fewer people or smaller teams.',
  infeasible: 'These settings cannot form any valid teams. Try a different team size.',
  no_solution_found: 'No teams were found in the time allowed. Try fewer people or smaller teams.',
}

export default function ResultsPage({ ctx }: { ctx: Ctx }) {
  const r = ctx.result
  if (!r) return <Notice>No teams yet.</Notice>
  const found = r.teams.length > 0
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold md:text-3xl">Your teams</h1>
        <button className="btn" onClick={ctx.newRun}>Make new teams</button>
      </div>
      {found
        ? <Notice kind={r.optimality_proven ? 'ok' : 'warn'}>{r.optimality_proven ? 'These are the best possible teams.' : 'These are the best teams found in the time allowed. Better teams may exist.'}</Notice>
        : <Notice kind="err">{NO_TEAMS[r.status] ?? 'No teams were found.'}</Notice>}
      {found && <div className="grid gap-3 md:grid-cols-2">{r.teams.map((t: any) => { const col = COLORS[(t.team - 1) % COLORS.length]; return (
        <section key={t.team} className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <h2 className="px-3 py-2 text-sm font-semibold text-white" style={{ background: col }}>Team {t.team}</h2>
          <div className="flex flex-wrap gap-1 p-3">{t.members.map((m: string) => <span key={m} className="rounded-full px-2 py-0.5 text-sm font-medium" style={{ background: col + '22', color: col }}>{m}</span>)}</div>
        </section>) })}</div>}
      {found && r.unassigned.length > 0 && <section className="card">
        <h2 className="mb-2 text-base font-semibold">Not in a team ({r.unassigned.length})</h2>
        <p className="text-sm">{r.unassigned.join(', ')}</p></section>}
    </div>
  )
}
