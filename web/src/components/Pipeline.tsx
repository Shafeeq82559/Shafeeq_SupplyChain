import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import type { StepEvent } from '../api'
import { tidy } from '../lib'
import { AGENTS } from './agents'


function useElapsed(running: boolean) {
  const [ms, setMs] = useState(0)
  useEffect(() => {
    if (!running) return
    const t0 = performance.now()
    const id = window.setInterval(() => setMs(performance.now() - t0), 100)
    return () => clearInterval(id)
  }, [running])
  return ms
}

/** Live view of the agent workflow: each agent lights up as the backend reports it finished. */
export function Pipeline({ events, running }: { events: StepEvent[]; running: boolean }) {
  const elapsed = useElapsed(running)
  const doneNodes = new Set(events.map((e) => e.node))
  const last = events.length ? AGENTS.findIndex((a) => a.node === events[events.length - 1].node) : -1
  const active = running ? Math.min(last + 1, AGENTS.length - 1) : -1
  const finished = !running && doneNodes.size === AGENTS.length
  const progress = finished ? 1 : Math.min(doneNodes.size / (AGENTS.length - 1), 1)
  const revised = events.filter((e) => e.node === 'response').length > 1

  return (
    <motion.section className="panel pipeline" aria-live="polite" aria-label="Agents at work"
      initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 0.8, 0.24, 1] }}>
      <div className="pipe-head">
        <h3>{finished ? 'All agents finished' : 'Agents at work'}</h3>
        <span className="pipe-clock num">{(elapsed / 1000).toFixed(1)}s</span>
      </div>

      <div className="pipe-scroll">
        <div className="pipe-lane">
          <div className="pipe-rail">
            <span className="pipe-track" />
            <motion.i className="pipe-fill" animate={{ width: `${progress * 100}%` }} transition={{ duration: 0.6, ease: [0.22, 0.8, 0.24, 1] }} />
            <motion.span className="pipe-cargo" aria-hidden="true" animate={{ left: `${progress * 100}%` }} transition={{ duration: 0.6, ease: [0.22, 0.8, 0.24, 1] }} />
          </div>
          <ol className="pipe-nodes">
            {AGENTS.map((a, i) => {
              const state = running ? (i <= last ? 'done' : i === active ? 'active' : 'idle') : doneNodes.has(a.node) ? 'done' : 'idle'
              return (
                <li key={a.node} className={state}>
                  <span className="pipe-dot">{state === 'done' && <svg viewBox="0 0 12 12"><path d="M2.5 6.3l2.4 2.4 4.6-5" /></svg>}</span>
                  <span className="pipe-label">{a.label}</span>
                </li>
              )
            })}
          </ol>
        </div>
      </div>

      <ul className="pipe-log">
        <AnimatePresence initial={false}>
          {events.map((e, i) => (
            <motion.li key={`${e.node}-${i}`} className="done" layout="position"
              initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.4, ease: [0.22, 0.8, 0.24, 1] }}>
              <span className="log-name">{e.step.agent}</span>
              <span className="log-ms num">{e.step.duration_ms >= 1000 ? `${(e.step.duration_ms / 1000).toFixed(1)}s` : `${e.step.duration_ms} ms`}</span>
              <span className="log-text">{tidy(e.step.summary)}</span>
            </motion.li>
          ))}
          {running && active >= 0 && (
            <motion.li key={`active-${AGENTS[active].node}-${events.length}`} className="working" layout="position"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
              <span className="log-spin" aria-hidden="true" />
              <span className="log-name">{AGENTS[active].label}</span>
              <span className="log-text">{AGENTS[active].doing}</span>
            </motion.li>
          )}
        </AnimatePresence>
      </ul>
      {revised && <p className="footnote" style={{ marginTop: 10 }}>The judge asked for a revision, so the plan was rewritten once.</p>}
    </motion.section>
  )
}
