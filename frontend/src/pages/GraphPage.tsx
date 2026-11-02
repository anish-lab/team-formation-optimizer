import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import type { Ctx } from '../App'
import { Card, Field, Notice, fmt } from '../components/ui'

const COLORS = ['#4f46e5', '#059669', '#d97706', '#db2777', '#0891b2', '#7c3aed', '#65a30d', '#dc2626', '#0d9488', '#9333ea']

export default function GraphPage({ ctx }: { ctx: Ctx }) {
  const r = ctx.result
  const ref = useRef<HTMLDivElement>(null)
  const [minC, setMinC] = useState(0.5)
  const [onlyTeam, setOnlyTeam] = useState(false)
  const [table, setTable] = useState(false)
  const edges = useMemo(() => (r ? r.graph.edges.filter((e: any) => (onlyTeam ? e.intra_team : e.intra_team || e.compat >= minC)) : []), [r, minC, onlyTeam])
  const tooBig = r ? r.graph.nodes.length > 150 || edges.length > 1500 : false

  useEffect(() => {
    if (!r || !ref.current || table || tooBig) return
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...r.graph.nodes.map((n: any) => ({ data: { id: n.id, label: `${n.id}\n${fmt(n.value, 2)}`, team: n.team } })),
        ...edges.map((e: any, i: number) => ({ data: { id: `e${i}`, source: e.source, target: e.target, compat: e.compat, intra: e.intra_team } })),
      ],
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 8, 'text-wrap': 'wrap', 'background-color': (n: any) => (n.data('team') === null || n.data('team') === undefined ? '#94a3b8' : COLORS[n.data('team') % COLORS.length]), color: '#64748b', 'text-valign': 'bottom' } },
        { selector: 'edge', style: { width: (e: any) => 0.5 + 2 * e.data('compat'), 'line-color': (e: any) => (e.data('intra') ? '#4f46e5' : '#cbd5e1'), opacity: 0.8 } },
      ] as any,
      layout: { name: 'cose', animate: false } as any,
    })
    cy.on('tap', 'edge', e => alert(`${e.target.data('source')} – ${e.target.data('target')}: compatibility ${fmt(e.target.data('compat'))}`))
    return () => cy.destroy()
  }, [r, edges, table, tooBig])

  if (!r) return <Notice>No result yet. Run an optimization first.</Notice>
  return (
    <Card title="Compatibility graph" right={<button className="btn-ghost" onClick={() => setTable(!table)}>{table ? 'Show graph' : 'Show table view'}</button>}>
      <div className="mb-3 grid gap-3 md:grid-cols-3">
        <Field label={`Show non-team edges with compatibility ≥ ${minC.toFixed(2)}`}><input type="range" min={0} max={1} step={0.05} value={minC} onChange={e => setMinC(Number(e.target.value))} className="w-full" /></Field>
        <label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={onlyTeam} onChange={e => setOnlyTeam(e.target.checked)} />Only edges inside teams</label>
        <div className="self-end text-xs text-slate-500">{r.graph.nodes.length} nodes · {edges.length} edges shown{r.graph.edges_truncated ? ' (edge list truncated server-side)' : ''}. Grey nodes: unassigned.</div></div>
      {tooBig && !table && <Notice kind="warn">Too many elements for a readable drawing — raise the edge filter or use the table view.</Notice>}
      {!table && !tooBig && <div ref={ref} className="h-[520px] rounded-lg border bg-white" aria-label="Compatibility graph" />}
      {(table || tooBig) && <div className="max-h-[480px] overflow-auto"><table className="w-full text-xs"><thead><tr><th className="text-left">Candidate A</th><th className="text-left">Candidate B</th><th className="text-left">Compatibility</th><th className="text-left">In same team</th></tr></thead>
        <tbody>{edges.slice(0, 1000).map((e: any, i: number) => <tr key={i} className="border-t"><td>{e.source}</td><td>{e.target}</td><td>{fmt(e.compat)}</td><td>{e.intra_team ? 'yes' : ''}</td></tr>)}</tbody></table></div>}
    </Card>
  )
}
