import { useEffect, useState } from 'react'
import { Hexagon, Moon, Sun } from 'lucide-react'
import type { Page } from './types'
import Wizard from './pages/Wizard'
import ResultsPage from './pages/ResultsPage'

export interface AppState { file: File | null; taskId: string | null; result: any }
export interface Ctx extends AppState { set: (p: Partial<AppState>) => void; go: (p: Page) => void; newRun: () => void }

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem('tf-theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])
  return [dark, () => setDark(d => !d)] as const
}

export default function App() {
  const [page, go] = useState<Page>('wizard')
  const [wizKey, setWizKey] = useState(0)
  const [dark, toggle] = useTheme()
  const [s, setS] = useState<AppState>({ file: null, taskId: null, result: null })
  const newRun = () => { setS({ file: null, taskId: null, result: null }); setWizKey(k => k + 1); go('wizard') }
  const ctx: Ctx = { ...s, set: p => setS(prev => ({ ...prev, ...p })), go, newRun }
  return (
    <div className="mx-auto min-h-screen max-w-5xl px-4 pb-10">
      <header className="flex items-center justify-between gap-2 py-4">
        <div className="flex items-center gap-2 text-lg font-extrabold text-indigo-700 dark:text-indigo-300"><Hexagon size={22} />CliqueCraft</div>
        <button onClick={toggle} className="rounded-lg p-2 hover:bg-slate-200 dark:hover:bg-slate-800" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
      </header>
      <main className="space-y-4">
        {page === 'wizard' && <Wizard key={wizKey} ctx={ctx} />}
        {page === 'results' && <ResultsPage ctx={ctx} />}
      </main>
    </div>
  )
}
