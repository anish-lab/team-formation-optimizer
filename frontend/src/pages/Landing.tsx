import { ArrowRight, BarChart3, Hexagon, ListChecks, Sparkles, UploadCloud } from 'lucide-react'

export default function Landing({ onStart }: { onStart: () => void }) {
  const steps = [
    { icon: UploadCloud, t: 'Upload', d: 'Drop in a CSV with one row per person.' },
    { icon: ListChecks, t: 'Answer a few questions', d: 'One at a time: which columns matter, what they mean, team size.' },
    { icon: BarChart3, t: 'Get your teams', d: 'An exact optimiser searches for the best groups and tells you if it is proven optimal.' },
  ]
  return (
    <div className="step-in">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 px-6 py-16 text-center text-white shadow-xl md:py-24">
        <div className="blob absolute -left-16 -top-16 h-72 w-72 rounded-full bg-white/10 blur-3xl" aria-hidden />
        <div className="blob absolute -bottom-20 -right-10 h-80 w-80 rounded-full bg-fuchsia-300/20 blur-3xl" style={{ animationDelay: '-4s' }} aria-hidden />
        <div className="relative mx-auto max-w-2xl">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/15 backdrop-blur"><Hexagon size={34} /></div>
          <h1 className="text-5xl font-extrabold tracking-tight md:text-6xl">CliqueCraft</h1>
          <p className="mt-3 text-lg text-indigo-100 md:text-xl">Teams crafted from compatibility — with proof, not guesswork.</p>
          <button onClick={onStart} className="mt-8 inline-flex items-center gap-2 rounded-full bg-white px-7 py-3 text-base font-semibold text-indigo-700 shadow-lg transition hover:scale-105 hover:shadow-xl focus:outline-none focus:ring-4 focus:ring-white/50">
            Get started <ArrowRight size={18} /></button>
          <p className="mt-3 flex items-center justify-center gap-1 text-xs text-indigo-100"><Sparkles size={12} /> Takes about a minute · your file never leaves your computer</p>
        </div>
      </section>
      <section className="mt-6 grid gap-4 md:grid-cols-3" aria-label="How it works">
        {steps.map((s, i) => (
          <div key={s.t} className="card text-center transition hover:-translate-y-1 hover:shadow-md" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"><s.icon size={22} /></div>
            <div className="text-xs font-semibold text-indigo-600 dark:text-indigo-300">STEP {i + 1}</div>
            <h2 className="mt-1 font-semibold">{s.t}</h2>
            <p className="mt-1 text-sm text-slate-600">{s.d}</p>
          </div>))}
      </section>
    </div>
  )
}
