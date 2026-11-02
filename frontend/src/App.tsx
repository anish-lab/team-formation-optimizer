import { useEffect, useState } from 'react'
import { Hexagon, Moon, Sun } from 'lucide-react'
import { defaultSettings, Feature, Page, Settings } from './types'
import Landing from './pages/Landing'
import Wizard from './pages/Wizard'
import ResultsPage from './pages/ResultsPage'
import GraphPage from './pages/GraphPage'
import EvaluationPage from './pages/EvaluationPage'
import ExportPage from './pages/ExportPage'

export interface AppState {
  file: File | null; features: Feature[]; idColumn: string; nRows: number; validated: boolean
  settings: Settings; taskId: string | null; result: any; config: any
}
export interface Ctx extends AppState { set: (p: Partial<AppState>) => void; go: (p: Page) => void }

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem('tf-theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])
  return [dark, () => setDark(d => !d)] as const
}

export default function App() {
  const [page, go] = useState<Page>('home')
  const [wizKey, setWizKey] = useState(0)
  const [dark, toggle] = useTheme()
  const [s, setS] = useState<AppState>({ file: null, features: [], idColumn: '', nRows: 0, validated: false, settings: defaultSettings, taskId: null, result: null, config: null })
  const ctx: Ctx = { ...s, set: p => setS(prev => ({ ...prev, ...p })), go }
  const hasResult = !!s.result
  const newRun = () => { setS(prev => ({ ...prev, result: null, taskId: null, validated: false })); setWizKey(k => k + 1); go('wizard') }
  const tabs: [Page, string, boolean][] = [['results', 'Results', hasResult], ['graph', 'Graph', hasResult], ['evaluation', 'Compare', hasResult], ['export', 'Export', hasResult]]
  return (
    <div className="mx-auto min-h-screen max-w-5xl px-4 pb-10">
      <header className="flex flex-wrap items-center justify-between gap-2 py-4">
        <button onClick={() => go('home')} className="flex items-center gap-2 text-lg font-extrabold text-indigo-700 dark:text-indigo-300" aria-label="CliqueCraft home"><Hexagon size={22} />CliqueCraft</button>
        <nav aria-label="Main" className="flex flex-wrap items-center gap-1 text-sm">
          {tabs.map(([p, label, on]) => <button key={p} disabled={!on} onClick={() => go(p)} aria-current={page === p ? 'page' : undefined}
            className={`rounded-lg px-3 py-1.5 transition disabled:opacity-40 ${page === p ? 'bg-indigo-100 font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' : 'hover:bg-slate-200 dark:hover:bg-slate-800'}`}>{label}</button>)}
          <button className="btn ml-1 py-1.5" onClick={newRun}>New teams</button>
          <button onClick={toggle} className="ml-1 rounded-lg p-2 hover:bg-slate-200 dark:hover:bg-slate-800" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
        </nav>
      </header>
      <main className="space-y-4">
        {page === 'home' && <Landing onStart={() => (s.result ? go('results') : newRun())} />}
        {page === 'wizard' && <Wizard key={wizKey} ctx={ctx} />}
        {page === 'results' && <ResultsPage ctx={ctx} />}
        {page === 'graph' && <GraphPage ctx={ctx} />}
        {page === 'evaluation' && <EvaluationPage ctx={ctx} />}
        {page === 'export' && <ExportPage ctx={ctx} />}
      </main>
    </div>
  )
}
