import { MotionConfig, motion } from 'motion/react'
import { useCallback, useEffect, useState } from 'react'
import { api, type Health, type Provider } from './api'
import { HistoryDrawer } from './components/HistoryDrawer'
import { Nav } from './components/Nav'
import { SideRails } from './components/SideRails'
import { PAGES, type PageId } from './components/pages'
import { useHistory, type HistoryEntry } from './history'
import { Analyze } from './pages/Analyze'
import { Cases } from './pages/Cases'
import { Evaluation } from './pages/Evaluation'
import { Insights } from './pages/Insights'
import { Predict } from './pages/Predict'
import { Prioritize } from './pages/Prioritize'
import { Risk } from './pages/Risk'

const pageFromHash = (): PageId => {
  const id = window.location.hash.replace('#/', '') as PageId
  return PAGES.some((p) => p.id === id) ? id : 'analyze'
}

export default function App() {
  const [page, setPage] = useState<PageId>(pageFromHash)
  const [health, setHealth] = useState<Health | null | undefined>(undefined) // undefined = still loading
  const [providers, setProviders] = useState<Provider[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [restore, setRestore] = useState<{ entry: HistoryEntry; n: number } | null>(null)
  const history = useHistory()

  const refresh = useCallback(async () => {
    try {
      const [h, p] = await Promise.all([api.health(), api.providers()])
      setHealth(h)
      setProviders(p.providers)
    } catch {
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    const first = window.setTimeout(refresh, 0)
    // the backend takes up to a minute to load its index and models after a restart: keep checking
    const t = window.setInterval(() => { if (!document.hidden) refresh() }, 15000)
    return () => { clearTimeout(first); clearInterval(t) }
  }, [refresh])

  useEffect(() => {
    const onHash = () => { setPage(pageFromHash()); window.scrollTo({ top: 0 }) }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id: PageId) => { window.location.hash = `#/${id}` }
  const openEntry = (entry: HistoryEntry) => { setRestore({ entry, n: Date.now() }); go('analyze') }
  const apiReady = !!health?.models_ready && !!health?.index_ready

  return (
    <MotionConfig reducedMotion="user">
      <Nav page={page} onNavigate={go} health={health} providers={providers} onChanged={refresh} historyCount={history.length} onHistory={() => setHistoryOpen(true)} />
      <SideRails page={page} />
      <HistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} onOpenEntry={openEntry} />
      <main id="content">
        {health === null && (
          <div className="notice error floating" role="alert">
            <div><b>The API isn't responding.</b> If you just started it, wait about 30 seconds for the index and models to load.{' '}
              <button className="link" onClick={refresh}>Retry now</button></div>
          </div>
        )}
        {page === 'analyze' ? (
          <Analyze apiReady={apiReady} restore={restore} />
        ) : (
          <motion.div key={page} className="subpage" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.22, 0.8, 0.24, 1] }}>
            {page === 'cases' && <Cases />}
            {page === 'prioritize' && <Prioritize />}
            {page === 'predict' && <Predict />}
            {page === 'risk' && <Risk />}
            {page === 'insights' && <Insights />}
            {page === 'evaluation' && <Evaluation />}
          </motion.div>
        )}
      </main>
    </MotionConfig>
  )
}
