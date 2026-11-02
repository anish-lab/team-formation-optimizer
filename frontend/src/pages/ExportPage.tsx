import { Download } from 'lucide-react'
import type { Ctx } from '../App'
import { Card, Notice } from '../components/ui'
import { api } from '../services/api'

const ITEMS: [string, string][] = [['teams_csv', 'Team assignments (CSV)'], ['unassigned_csv', 'Unassigned candidates (CSV)'], ['json', 'Assignments + full configuration (JSON)'],
  ['stats_json', 'Optimization statistics (JSON)'], ['summary_txt', 'Human-readable experiment summary']]

export default function ExportPage({ ctx }: { ctx: Ctx }) {
  if (!ctx.taskId || !ctx.result) return <Notice>Nothing to export yet. Run an optimization first.</Notice>
  return (
    <Card title="Export">
      <p className="mb-3 text-xs text-slate-600">Exports contain candidate IDs and scores plus the configuration needed to reproduce the run (feature schema, objective, size rules, solver settings, termination status) — not the raw CSV.</p>
      <div className="flex flex-wrap gap-2">{ITEMS.map(([f, l]) => <a key={f} className="btn-ghost" href={api.exportUrl(ctx.taskId!, f)} download><Download size={14} />{l}</a>)}</div>
    </Card>
  )
}
