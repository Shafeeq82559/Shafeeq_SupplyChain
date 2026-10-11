import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { clearHistory, removeHistory, timeAgo, useHistory, type HistoryEntry } from '../history'
import { PRIORITY_COLOR } from '../lib'
import { ease } from './motionkit'

export function HistoryDrawer({ open, onClose, onOpenEntry }: { open: boolean; onClose: () => void; onOpenEntry: (e: HistoryEntry) => void }) {
  const items = useHistory()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} />
          <motion.aside className="drawer" role="dialog" aria-modal="true" aria-label="Analysis history"
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ duration: 0.4, ease }}>
            <header>
              <h3>History</h3>
              <span className="muted">{items.length ? `${items.length} saved on this device` : ''}</span>
              <button className="iconbtn" onClick={onClose} aria-label="Close history"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
            </header>
            {items.length === 0 ? (
              <div className="drawer-empty">
                <b>No analyses yet</b>
                <p>Every analysis you run is saved here, so you can reopen the full briefing without running it again.</p>
              </div>
            ) : (
              <>
                <ul className="hist">
                  {items.map((e, i) => (
                    <motion.li key={e.id} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.35, delay: 0.05 + i * 0.04, ease }}>
                      <button className="hist-main" onClick={() => { onOpenEntry(e); onClose() }}>
                        <span className="hist-top">
                          <i className="hist-dot" style={{ background: PRIORITY_COLOR[e.level] ?? 'var(--muted)' }} />
                          <b>{e.title}</b>
                          <time>{timeAgo(e.ts)}</time>
                        </span>
                        <span className="hist-q">{e.query}</span>
                        <span className="hist-meta">{e.level} {e.label} · {e.strategy}</span>
                      </button>
                      <button className="iconbtn sm" onClick={() => removeHistory(e.id)} aria-label={`Delete ${e.title}`}><svg viewBox="0 0 24 24"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12" /></svg></button>
                    </motion.li>
                  ))}
                </ul>
                <footer><button className="btn ghost" onClick={clearHistory}>Clear all history</button></footer>
              </>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
