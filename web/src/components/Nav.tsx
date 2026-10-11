import { AnimatePresence, motion, useScroll, useSpring } from 'motion/react'
import { useEffect, useState } from 'react'
import { api, type Health, type Provider } from '../api'
import { LLM_LABELS } from '../lib'
import { useTheme } from '../theme'
import { PAGES, type PageId } from './pages'

export function Nav({ page, onNavigate, health, providers, onChanged, historyCount, onHistory }: {
  page: PageId; onNavigate: (p: PageId) => void; health: Health | null | undefined; providers: Provider[]; onChanged: () => void
  historyCount: number; onHistory: () => void
}) {
  const { scrollYProgress } = useScroll()
  const progress = useSpring(scrollYProgress, { stiffness: 140, damping: 28, restDelta: 0.001 })
  const [solid, setSolid] = useState(false)
  const [busy, setBusy] = useState(false)
  const { theme, toggle } = useTheme()

  useEffect(() => {
    const on = () => setSolid(window.scrollY > 32 || page !== 'analyze')
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [page])

  const ready = !!health?.models_ready && !!health?.index_ready
  const state = health === undefined ? 'idle' : health === null ? 'down' : ready ? 'ok' : 'warn'
  const label = health === undefined ? 'Connecting' : health === null ? 'API offline' : ready ? 'Ready' : 'Loading models'

  const options = [...providers.filter((p) => p.available && p.provider !== 'ollama').map((p) => p.provider), 'off']
  const current = health && !health.llm.enabled ? 'off' : providers.find((p) => p.active)?.provider ?? 'off'
  const pick = async (provider: string) => {
    if (provider === current || busy) return
    setBusy(true)
    try { await api.setProvider(provider) } finally { setBusy(false); onChanged() }
  }

  return (
    <header className={`nav ${solid ? 'solid' : ''}`}>
      <button className="brand" onClick={() => onNavigate('analyze')} aria-label="Disruption Assistant home">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="8" fill="currentColor" opacity=".14" />
          <rect x="7" y="11" width="18" height="10" rx="1.5" fill="#f2a900" />
          <path d="M12 11v10M16 11v10M20 11v10" stroke="#0e1b28" strokeWidth="1.4" />
          <path d="M4 25h24" stroke="currentColor" strokeWidth="1.6" strokeDasharray="3 2" opacity=".7" />
        </svg>
        <span>Disruption Assistant</span>
      </button>

      <nav className="nav-links" aria-label="Pages">
        {PAGES.map((p) => (
          <button key={p.id} className="nav-link" aria-current={p.id === page ? 'page' : undefined} onClick={() => onNavigate(p.id)} title={p.built ? p.title : `${p.title} (coming soon)`}>
            {p.id === page && <motion.span layoutId="nav-active" className="nav-active" transition={{ type: 'spring', stiffness: 500, damping: 38 }} />}
            <span className="lbl">{p.label}</span>
          </button>
        ))}
      </nav>

      <div className="nav-tools">
        <button className="themebtn" onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} title={theme === 'dark' ? 'Light theme' : 'Dark theme'}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.svg key={theme} viewBox="0 0 24 24" initial={{ rotate: -70, scale: 0.4, opacity: 0 }} animate={{ rotate: 0, scale: 1, opacity: 1 }} exit={{ rotate: 70, scale: 0.4, opacity: 0 }} transition={{ duration: 0.22 }}>
              {theme === 'dark'
                ? <><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" /></>
                : <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />}
            </motion.svg>
          </AnimatePresence>
        </button>
        <button className="histbtn" onClick={onHistory} aria-label={`History, ${historyCount} saved`}>
          <svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.7M4 4v4.7h4.7M12 8v4.5l3 1.8" /></svg>History{historyCount > 0 && <b className="num">{historyCount}</b>}
        </button>
        <span className={`sys ${state}`} title={health ? `LLM: ${health.llm.enabled ? health.llm.model : 'templates only'} · index ${health.index_ready ? 'ready' : 'loading'} · models ${health.models_ready ? 'ready' : 'loading'}` : 'Cannot reach the API'}>
          <i />{label}
        </span>
        {providers.length > 0 && (
          <label className="llm">
            <span className="sr-only">Language model</span>
            <select value={current} disabled={busy} onChange={(e) => pick(e.target.value)}>
              {options.map((o) => <option key={o} value={o}>{LLM_LABELS[o] ?? o}</option>)}
            </select>
          </label>
        )}
      </div>
      <motion.i className="scrollbar" style={{ scaleX: progress }} aria-hidden="true" />
    </header>
  )
}
