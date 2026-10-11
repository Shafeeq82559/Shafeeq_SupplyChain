import { AnimatePresence, motion, useScroll, useTransform } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Analysis, type Overrides, type StepEvent } from '../api'
import { Hero } from '../components/Hero'
import { SelectField } from '../components/ui'
import { addHistory, type HistoryEntry } from '../history'
import { Pipeline } from '../components/Pipeline'
import { Results } from '../components/Results'
import { EXAMPLES, INDUSTRIES, REGIONS, SIZES, TYPES } from '../lib'

type Backup = 'unknown' | 'yes' | 'no'
interface Details {
  type: string; industry: string; region: string; tier: string; size: string; severity: string; backup: Backup; impact: string
}
const EMPTY: Details = { type: '', industry: '', region: '', tier: '', size: '', severity: '', backup: 'unknown', impact: '' }

function toOverrides(d: Details): Overrides {
  const o: Overrides = {}
  if (d.type) o.disruption_type = d.type
  if (d.industry) o.industry = d.industry
  if (d.region) o.supplier_region = d.region
  if (d.tier) o.supplier_tier = Number(d.tier)
  if (d.size) o.supplier_size = d.size
  if (d.severity) o.disruption_severity = Number(d.severity)
  if (d.backup !== 'unknown') o.has_backup_supplier = d.backup === 'yes'
  return o
}

const SEVERITY_WORDS: Record<string, string> = {
  '1': 'It is a minor, brief slowdown.', '2': 'There are moderate delays.', '3': 'Output is significantly disrupted.',
  '4': 'Production is severely halted for weeks.', '5': 'It is a catastrophic complete shutdown expected to last months.',
}

/** A plain-English description built from the details form, for when the user leaves the text box empty. */
function describeFromDetails(d: Details): string {
  const who = ['a', d.tier && `Tier-${d.tier}`, d.size && d.size.toLowerCase(), d.industry, 'supplier'].filter(Boolean).join(' ')
  return [`${d.type} disruption affecting ${who}${d.region ? ` in ${d.region}` : ''}.`, d.severity && SEVERITY_WORDS[d.severity],
    d.backup === 'yes' ? 'We have a backup supplier.' : d.backup === 'no' ? 'We have no backup supplier.' : ''].filter(Boolean).join(' ')
}

export function Analyze({ apiReady, restore }: { apiReady: boolean; restore: { entry: HistoryEntry; n: number } | null }) {
  const shared = new URLSearchParams(window.location.search).get('q') ?? ''
  const [query, setQuery] = useState(shared)
  const [example, setExample] = useState<string | null>(null)
  const [details, setDetails] = useState<Details>(EMPTY)
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState<StepEvent[]>([])
  const [runId, setRunId] = useState(0)
  const [showPipeline, setShowPipeline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ a: Analysis; used: Overrides } | null>(null)
  const abort = useRef<AbortController | null>(null)
  const pipeRef = useRef<HTMLDivElement>(null)
  const resultRef = useRef<HTMLDivElement>(null)
  const autoRan = useRef(false)

  // the composer rises into view as the hero scrolls away
  const beginRef = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({ target: beginRef, offset: ['start end', 'start 42%'] })
  const y = useTransform(scrollYProgress, [0, 1], [90, 0])
  const opacity = useTransform(scrollYProgress, [0, 0.7], [0, 1])
  const scale = useTransform(scrollYProgress, [0, 1], [0.95, 1])

  const run = async () => {
    abort.current?.abort()
    const ctl = (abort.current = new AbortController())
    const profile = toOverrides(details)
    // no (usable) description but a disruption type chosen: describe the disruption from the details instead
    const text = details.type && query.trim().length < 12 ? describeFromDetails(details) : query
    setRunning(true); setError(null); setEvents([]); setResult(null); setShowPipeline(true); setRunId((n) => n + 1)
    requestAnimationFrame(() => pipeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    try {
      const a = await api.analyzeStream(text, profile, Number(details.impact) || undefined,
        (e) => setEvents((prev) => [...prev, e]), ctl.signal)
      setRunning(false)
      // let the finished pipeline sit for a moment, then reveal the briefing
      await new Promise((r) => setTimeout(r, 900))
      if (abort.current !== ctl) return
      setResult({ a, used: profile })
      addHistory(a, profile)
      setShowPipeline(false)
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      setRunning(false); setShowPipeline(false)
      setError(e instanceof ApiError ? (/does not appear to be about/.test(e.message) ? `${e.message} Describe what happened in a sentence, or clear the text box and choose a disruption type under the details.` : e.message) : 'Something went wrong. Try again.')
    }
  }

  // shareable link: ?q=<description> runs the analysis once the backend is ready
  useEffect(() => {
    if (shared && apiReady && !autoRan.current) { autoRan.current = true; run() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiReady])

  // reopen an analysis from history without running it again
  useEffect(() => {
    if (!restore) return
    setQuery(restore.entry.query); setResult({ a: restore.entry.a, used: restore.entry.used }); setShowPipeline(false); setError(null)
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 350)
  }, [restore])

  const set = <K extends keyof Details>(k: K, v: Details[K]) => setDetails((d) => ({ ...d, [k]: v }))
  const canRun = query.trim().length >= 3 || !!details.type
  const fromDetails = !!details.type && query.trim().length < 12
  const filled = Object.entries(details).some(([k, v]) => (k === 'backup' ? v !== 'unknown' : v !== ''))

  return (
    <>
      <Hero />

      <section className="begin" id="begin" ref={beginRef}>
        <div className="begin-grid">
        <motion.div className="panel composer" style={{ y, opacity, scale }}>
          <h2>What happened?</h2>
          <p className="lede">Describe the disruption in plain language. The agents take it from there.</p>
          <div className="chips" role="group" aria-label="Examples">
            {Object.keys(EXAMPLES).map((k) => (
              <button key={k} className="chip" aria-pressed={example === k} onClick={() => { setExample(k); setQuery(EXAMPLES[k]) }}>{k}</button>
            ))}
          </div>
          <label className="sr-only" htmlFor="query">Describe the disruption</label>
          <textarea id="query" className="query" value={query} placeholder="e.g. Flooding closed our Tier-1 resin supplier in Thailand; no backup, output down by half."
            onChange={(e) => { setQuery(e.target.value); setExample(null) }}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canRun && !running) run() }} />

          <div className="composer-foot">
            <button className="btn" onClick={run} disabled={!canRun || running || !apiReady}>
              {running ? 'Analyzing' : 'Analyze disruption'}
            </button>
            {running && <button className="btn ghost" onClick={() => { abort.current?.abort(); setRunning(false); setShowPipeline(false) }}>Cancel</button>}
            {!apiReady && !running && <span className="muted">Waiting for the API to finish loading.</span>}
            {!canRun && !running && <span className="muted">Describe what happened, or choose at least a disruption type under the details below.</span>}
            {canRun && fromDetails && !running && <span className="muted">No description entered, so the analysis will use your details.</span>}
            <span className="muted hint">Ctrl + Enter to run</span>
          </div>

          <div className="details">
            <button className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? 'Hide details you already know' : 'Add details you already know'}{filled && !open ? ' (some set)' : ''}
            </button>
            <AnimatePresence initial={false}>
              {open && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.28, ease: [0.22, 0.8, 0.24, 1] }} style={{ overflow: 'hidden' }}>
                  <p className="muted" style={{ marginTop: 10 }}>These override what the agents infer from the text.</p>
                  <div className="details-body">
                    <SelectField empty="Not specified" label="Type" value={details.type} options={TYPES} onChange={(v) => set('type', v)} />
                    <SelectField empty="Not specified" label="Industry" value={details.industry} options={INDUSTRIES} onChange={(v) => set('industry', v)} />
                    <SelectField empty="Not specified" label="Region" value={details.region} options={REGIONS} onChange={(v) => set('region', v)} />
                    <SelectField empty="Not specified" label="Tier" value={details.tier} options={['1', '2', '3', '4']} onChange={(v) => set('tier', v)} />
                    <SelectField empty="Not specified" label="Size" value={details.size} options={SIZES} onChange={(v) => set('size', v)} />
                    <SelectField empty="Not specified" label="Severity" value={details.severity} options={['1', '2', '3', '4', '5']} onChange={(v) => set('severity', v)} />
                    <div className="field">
                      Backup supplier
                      <div className="tri fit" role="group" aria-label="Backup supplier">
                        {(['unknown', 'yes', 'no'] as Backup[]).map((b) => (
                          <button key={b} aria-pressed={details.backup === b} onClick={() => set('backup', b)}>{b === 'unknown' ? 'Unknown' : b === 'yes' ? 'Yes' : 'No'}</button>
                        ))}
                      </div>
                    </div>
                    <label className="field">Observed impact % (optional)
                      <input type="number" min={0} max={100} value={details.impact} onChange={(e) => set('impact', e.target.value)} />
                    </label>
                  </div>
                  <button className="btn ghost" onClick={() => setDetails(EMPTY)} disabled={!filled}>Clear all details</button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
        </div>
      </section>

      <div className="wrap results-zone">
        <div ref={pipeRef} style={{ scrollMarginTop: 84 }}>
          <AnimatePresence>{showPipeline && <Pipeline key={runId} events={events} running={running} />}</AnimatePresence>
        </div>
        {error && !running && <div className="notice error" role="alert"><div><b>Analysis failed.</b> {error}</div></div>}
        {result && !running && (
          <div ref={resultRef} style={{ scrollMarginTop: 84 }}>
            <Results key={result.a.query + result.a.total_duration_ms} a={result.a} used={result.used} />
          </div>
        )}
      </div>
    </>
  )
}
