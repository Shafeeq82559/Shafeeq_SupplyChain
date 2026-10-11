import { motion } from 'motion/react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError, type Evaluation, type SearchHit, type SearchResponse } from '../api'
import { RespChip } from '../components/bits'
import { RESP_HUE } from '../components/chartkit'
import { Donut, Scatter } from '../components/charts2'
import { Facet, SeverityPicker } from '../components/Facet'
import { ease, rise } from '../components/motionkit'
import { Empty, PageHead, Segmented, Skeleton, Slider, Toggle } from '../components/ui'
import { INDUSTRIES, money, pct, REGIONS, RESPONSES, TYPES } from '../lib'

const MODES = [{ id: 'hybrid', label: 'Hybrid' }, { id: 'semantic', label: 'Meaning' }, { id: 'keyword', label: 'Keywords' }] as const
type Mode = (typeof MODES)[number]['id']
const SORTS = [{ id: 'match', label: 'Best match' }, { id: 'recovery', label: 'Fastest recovery' }, { id: 'loss', label: 'Lowest loss' }, { id: 'impact', label: 'Highest impact' }] as const
type Sort = (typeof SORTS)[number]['id']
type Val = string | number

const IDEAS = [
  { q: 'ransomware attack on an electronics supplier in Asia', note: 'Cyber attack' },
  { q: 'typhoon flooded our semiconductor plant in Taiwan', note: 'Natural disaster' },
  { q: 'dock workers strike delaying pharma ingredients', note: 'Labor strike' },
  { q: 'export sanctions blocked titanium deliveries', note: 'Geopolitical' },
  { q: 'port congestion holding containers of consumer goods', note: 'Port congestion' },
  { q: 'factory fire stopped production at an auto parts plant', note: 'Factory incident' },
]
const SEV_COLORS = ['#2e7d5b', '#8aa93a', '#d9a400', '#d9711c', '#c2452d']
const STOP = ['with', 'that', 'from', 'this', 'have', 'into', 'were', 'what', 'their', 'there']
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); const m = Math.floor(s.length / 2); return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : 0 }

/** Wraps the words you searched for in <mark>, so you can see why a case matched. */
function Marked({ text, query }: { text: string; query: string }) {
  const words = [...new Set(query.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 3 && !STOP.includes(w)))]
  if (!words.length) return <>{text}</>
  const parts = text.split(new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi'))
  return <>{parts.map((p, i) => (words.includes(p.toLowerCase()) ? <mark key={i}>{p}</mark> : <Fragment key={i}>{p}</Fragment>))}</>
}

function MatchRing({ value }: { value: number }) {
  const r = 17, L = 2 * Math.PI * r
  return (
    <div className="matchring" title={`Match ${value.toFixed(2)} (1.00 = ranked first by every method used)`}>
      <svg viewBox="0 0 44 44"><circle cx="22" cy="22" r={r} className="mr-track" />
        <motion.circle cx="22" cy="22" r={r} className="mr-bar" strokeDasharray={L} initial={{ strokeDashoffset: L }} animate={{ strokeDashoffset: L * (1 - Math.min(value, 1)) }} transition={{ duration: 0.9, delay: 0.2, ease }} /></svg>
      <b className="num">{Math.round(value * 100)}</b><small>match</small>
    </div>
  )
}

/** Day 0 to full recovery for one case, on the same scale for every case in the list. */
function Timeline({ h, max, delay }: { h: SearchHit; max: number; delay: number }) {
  const resp = h.response_time_days ?? 0, part = h.partial_recovery_days ?? 0, full = h.full_recovery_days
  const at = (d: number) => `${Math.min((100 * d) / max, 100)}%`
  return (
    <div className="timeline2" role="img" aria-label={`Response after ${resp} days, partly recovered by day ${part}, fully recovered by day ${full}`}>
      <div className="tl-track">
        <motion.i className="seg a" style={{ left: 0, width: at(resp) }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.6, delay, ease }} />
        <motion.i className="seg b" style={{ left: at(resp), width: `calc(${at(part)} - ${at(resp)})` }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.7, delay: delay + 0.1, ease }} />
        <motion.i className="seg c" style={{ left: at(part), width: `calc(${at(full)} - ${at(part)})` }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: delay + 0.2, ease }} />
        <span className="tl-dot" style={{ left: at(resp) }} /><span className="tl-dot" style={{ left: at(part) }} /><span className="tl-dot end" style={{ left: at(full) }} />
      </div>
      <div className="tl-legend"><span><i className="a" />responded day {resp}</span><span><i className="b" />partly back day {part}</span><span><i className="c" />fully back day {full}</span></div>
    </div>
  )
}

function CaseFile({ h, i, query, maxDays, maxImpact, fastest, open, toggle }: {
  h: SearchHit; i: number; query: string; maxDays: number; maxImpact: number; fastest: boolean; open: boolean; toggle: () => void
}) {
  const sev = SEV_COLORS[Math.min(Math.max(h.disruption_severity, 1), 5) - 1]
  return (
    <motion.article className="casefile" style={{ ['--h' as string]: RESP_HUE[h.response_type] ?? '#5c6e7c' }} initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.08 + Math.min(i, 8) * 0.06, ease }}>
      <header>
        <span className="cf-rank num">{i + 1}</span>
        <div className="cf-id">
          <div className="cf-line"><b className="cid">{h.disruption_id}</b><RespChip r={h.response_type} />
            {h.matchRank === 1 && <span className="ribbon sea">Closest match</span>}{fastest && <span className="ribbon green">Fastest recovery here</span>}</div>
          <div className="cf-tags">
            <span>{h.disruption_type}</span><span>{h.industry}</span><span>{h.supplier_region}</span><span>Tier {h.supplier_tier}</span>
            {h.supplier_size && <span>{h.supplier_size}</span>}<span className={h.has_backup_supplier ? 'good' : 'warn'}>{h.has_backup_supplier ? 'Had a backup' : 'No backup'}</span>
          </div>
        </div>
        {h.hybrid_score != null && <MatchRing value={h.hybrid_score} />}
      </header>

      {h.narrative && (
        <blockquote className={open ? 'open' : ''}>
          <p><Marked text={h.narrative} query={query} /></p>
          <button onClick={toggle}>{open ? 'Show less' : 'Read the full case'}</button>
        </blockquote>
      )}

      <div className="cf-tiles">
        <div><small>Severity</small><span className="sevdots">{[1, 2, 3, 4, 5].map((n) => <i key={n} style={n <= h.disruption_severity ? { background: sev } : undefined} />)}</span><b className="sevlabel" style={{ ['--sevc' as string]: sev }}>{h.disruption_severity} of 5</b></div>
        <div><small>Production hit</small><span className="bar"><motion.i style={{ width: `${(100 * h.production_impact_pct) / maxImpact}%` }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: 0.25 + i * 0.04, ease }} /></span><b className="num">{h.production_impact_pct.toFixed(0)}%</b></div>
        <div><small>Revenue lost</small><b className="num big">{money(h.revenue_loss_usd)}</b></div>
        <div><small>Switched supplier</small><b className={h.permanent_supplier_change ? 'warn' : 'good'}>{h.permanent_supplier_change ? 'Yes, for good' : 'No'}</b></div>
      </div>
      <Timeline h={h} max={maxDays} delay={0.3 + i * 0.04} />
    </motion.article>
  )
}

function SearchQuality() {
  const [ev, setEv] = useState<Evaluation | null | undefined>(undefined)
  const load = () => { if (ev === undefined) api.evaluation().then(setEv).catch(() => setEv(null)) }
  const s = ev?.search_eval
  const key = 'loose (type + industry)'
  const hybrid = s?.results['hybrid a=0.6 (default)']?.[key]
  const kw = s?.results.keyword?.[key], sem = s?.results.semantic?.[key]
  const filtersOk = s ? Object.values(s.filters).every((f) => f.results_breaking_a_filter === 0) : false
  return (
    <details className="fold quality" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) load() }}>
      <summary>How does this search work, and how accurate is it?</summary>
      <div className="fold-body">
        <ol className="how">
          <li><b>Meaning.</b> Every case narrative was turned into a vector by a small embedding model that runs on this machine. Your query becomes a vector too, and the closest cases win.</li>
          <li><b>Keywords.</b> A classic BM25 index scores exact words, which catches names and terms that the embedding blurs.</li>
          <li><b>Hybrid.</b> The two rankings are fused (reciprocal rank fusion) and the slider sets how much each counts. Filters apply before ranking.</li>
        </ol>
        <p className="footnote" style={{ marginTop: 6 }}>No language model is involved. The one exception is "Filter by detected type", which asks the classifier to read your query (it uses keyword rules when no model is available).</p>
        {ev === undefined && <p className="muted">Open this to load the test results.</p>}
        {s && hybrid && kw && sem && (
          <div className="qgrid">
            <p className="muted" style={{ gridColumn: '1 / -1' }}>Tested on {s.n_queries} searches. Of the top 10 results, how many had the right disruption type and industry:</p>
            {([['Keywords only', kw], ['Meaning only', sem], ['Hybrid', hybrid]] as const).map(([name, m]) => (
              <div key={name} className={name === 'Hybrid' ? 'qcard best' : 'qcard'}>
                <b className="num">{(m['precision@10'] * 10).toFixed(1)}<small> of 10</small></b><span>{name}</span>
                <small>{pct(m['hit@1'])} had a right case first · likely between {(m.ci95[0] * 10).toFixed(1)} and {(m.ci95[1] * 10).toFixed(1)}</small>
              </div>
            ))}
            <p className="muted" style={{ gridColumn: '1 / -1' }}>Typical speed {s.latency['hybrid a=0.6 (default)'].p50_ms} ms (95% under {s.latency['hybrid a=0.6 (default)'].p95_ms} ms). {filtersOk ? 'No result ever broke a filter in the filter tests.' : 'Some results broke a filter in the filter tests.'}</p>
          </div>
        )}
        {ev !== undefined && !s && <p className="muted">No search evaluation is saved yet. Run <code>python -m evaluation.search_eval</code>.</p>}
      </div>
    </details>
  )
}

export function Cases() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>('hybrid')
  const [alpha, setAlpha] = useState(0.6)
  const [topK, setTopK] = useState(10)
  const [auto, setAuto] = useState(false)
  const [types, setTypes] = useState<Val[]>([])
  const [industries, setIndustries] = useState<Val[]>([])
  const [regions, setRegions] = useState<Val[]>([])
  const [tiers, setTiers] = useState<Val[]>([])
  const [sizes, setSizes] = useState<Val[]>([])
  const [responses, setResponses] = useState<Val[]>([])
  const [backup, setBackup] = useState<Val[]>([])
  const [sev, setSev] = useState<[number, number]>([1, 5])
  const [sort, setSort] = useState<Sort>('match')
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [counts, setCounts] = useState<{ types: Record<string, number>; industries: Record<string, number> }>({ types: {}, industries: {} })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [res, setRes] = useState<{ r: SearchResponse; q: string } | null>(null)
  const ctl = useRef<AbortController | null>(null)

  useEffect(() => {
    api.stats().then((s) => setCounts({
      types: Object.fromEntries(Object.entries(s.by_disruption_type).map(([k, v]) => [k, v.count])),
      industries: Object.fromEntries(Object.entries(s.by_industry).map(([k, v]) => [k, v.count])),
    })).catch(() => undefined)
  }, [])

  const active: { label: string; clear: () => void }[] = [
    ...types.map((v) => ({ label: String(v), clear: () => setTypes(types.filter((x) => x !== v)) })),
    ...industries.map((v) => ({ label: String(v), clear: () => setIndustries(industries.filter((x) => x !== v)) })),
    ...regions.map((v) => ({ label: String(v), clear: () => setRegions(regions.filter((x) => x !== v)) })),
    ...tiers.map((v) => ({ label: `Tier ${v}`, clear: () => setTiers(tiers.filter((x) => x !== v)) })),
    ...sizes.map((v) => ({ label: `${v} supplier`, clear: () => setSizes(sizes.filter((x) => x !== v)) })),
    ...responses.map((v) => ({ label: String(v), clear: () => setResponses(responses.filter((x) => x !== v)) })),
    ...backup.map((v) => ({ label: String(v), clear: () => setBackup([]) })),
    ...(sev[0] > 1 || sev[1] < 5 ? [{ label: sev[0] === sev[1] ? `Severity ${sev[0]}` : `Severity ${sev[0]} to ${sev[1]}`, clear: () => setSev([1, 5]) }] : []),
  ]
  const clearAll = () => { setTypes([]); setIndustries([]); setRegions([]); setTiers([]); setSizes([]); setResponses([]); setBackup([]); setSev([1, 5]) }

  const search = async (text = query) => {
    ctl.current?.abort()
    const c = (ctl.current = new AbortController())
    const filters: Record<string, unknown> = {}
    if (types.length) filters.disruption_type = types
    if (industries.length) filters.industry = industries
    if (regions.length) filters.supplier_region = regions
    if (tiers.length) filters.supplier_tier = tiers
    if (sizes.length) filters.supplier_size = sizes
    if (responses.length) filters.response_type = responses
    if (backup.length) filters.has_backup_supplier = backup[0] === 'Had a backup supplier'
    if (sev[0] > 1 || sev[1] < 5) { filters.min_severity = sev[0]; filters.max_severity = sev[1] }
    setLoading(true); setError(null); setOpen(new Set())
    try {
      const r = await api.search({ query: text, top_k: topK, mode, alpha, auto_filter: auto, filters }, c.signal)
      setRes({ r: { ...r, results: r.results.map((h, i) => ({ ...h, matchRank: i + 1 })) }, q: text })
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(e instanceof ApiError ? e.message : 'Search failed. Try again.')
    } finally {
      if (ctl.current === c) setLoading(false)
    }
  }

  const hits = useMemo(() => {
    const list = [...(res?.r.results ?? [])]
    const by: Record<Sort, (a: SearchHit, b: SearchHit) => number> = {
      match: (a, b) => (a.matchRank ?? 0) - (b.matchRank ?? 0), recovery: (a, b) => a.full_recovery_days - b.full_recovery_days,
      loss: (a, b) => a.revenue_loss_usd - b.revenue_loss_usd, impact: (a, b) => b.production_impact_pct - a.production_impact_pct,
    }
    return list.sort(by[sort])
  }, [res, sort])

  const stats = useMemo(() => {
    const h = res?.r.results ?? []
    if (!h.length) return null
    const mix = Object.entries(h.reduce<Record<string, number>>((m, x) => ({ ...m, [x.response_type]: (m[x.response_type] ?? 0) + 1 }), {})).sort((a, b) => b[1] - a[1])
    const fastest = h.reduce((a, b) => (b.full_recovery_days < a.full_recovery_days ? b : a))
    return { mix, top: mix[0], recovery: median(h.map((x) => x.full_recovery_days)), impact: median(h.map((x) => x.production_impact_pct)), switched: h.filter((x) => x.permanent_supplier_change).length / h.length, fastest }
  }, [res])
  const maxDays = Math.max(...hits.map((h) => h.full_recovery_days), 1)
  const maxImpact = Math.max(...hits.map((h) => h.production_impact_pct), 1)

  return (
    <div className="wrap page-body">
      <PageHead title="Search past disruptions" lede="Describe a disruption in your own words. The closest of 100,000 recorded cases come back with how each one was handled and how long it took to recover." />

      <motion.section className="panel searchbox" {...rise(1)}>
        <form onSubmit={(e) => { e.preventDefault(); if (query.trim().length >= 3) search() }}>
          <div className="searchrow">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></svg>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. ransomware attack on an electronics supplier in Asia" aria-label="Search query" />
            <button className="btn" type="submit" disabled={query.trim().length < 3 || loading}>{loading ? 'Searching' : 'Search cases'}</button>
          </div>
        </form>

        <div className="dock" role="group" aria-label="Filters">
          <span className="dock-title">Narrow it down</span>
          <Facet label="Type" options={TYPES} value={types} onChange={setTypes} counts={counts.types} />
          <Facet label="Industry" options={INDUSTRIES} value={industries} onChange={setIndustries} counts={counts.industries} />
          <Facet label="Region" options={REGIONS} value={regions} onChange={setRegions} />
          <Facet label="Tier" options={[1, 2, 3, 4]} value={tiers} onChange={setTiers} />
          <Facet label="Size" options={['Small', 'Medium', 'Large']} value={sizes} onChange={setSizes} />
          <Facet label="Response" options={RESPONSES} value={responses} onChange={setResponses} />
          <Facet label="Backup" options={['Had a backup supplier', 'No backup supplier']} value={backup} onChange={setBackup} single />
          <SeverityPicker min={sev[0]} max={sev[1]} onChange={(a, b) => setSev([a, b])} />
        </div>
        {active.length > 0 && (
          <div className="activebar">
            {active.map((a) => <button key={a.label} className="achip" onClick={a.clear} aria-label={`Remove filter ${a.label}`}>{a.label}<svg viewBox="0 0 12 12"><path d="M3 3l6 6M9 3L3 9" /></svg></button>)}
            <button className="link" onClick={clearAll}>Clear all</button>
          </div>
        )}

        <div className="controls">
          <div className="field">How to match<Segmented label="Retrieval mode" value={mode} options={MODES} onChange={setMode} /></div>
          <Slider label="Meaning vs keywords" value={alpha} min={0} max={1} step={0.05} onChange={setAlpha} format={(v) => `${Math.round(v * 100)}% meaning`} disabled={mode !== 'hybrid'} />
          <Slider label="Cases to show" value={topK} min={5} max={30} onChange={setTopK} />
          <Toggle label="Filter by detected type" hint="reads your query" checked={auto} onChange={setAuto} />
        </div>
      </motion.section>

      {loading && <div className="stackgap"><Skeleton h={120} /><Skeleton h={260} /><Skeleton h={260} /></div>}
      {error && !loading && <div className="notice error" role="alert"><div><b>Search failed.</b> {error}</div></div>}

      {!res && !loading && !error && (
        <>
          <h3 className="subhead big">Not sure where to start? Try one of these</h3>
          <div className="ideas">
            {IDEAS.map((x, i) => (
              <motion.button key={x.q} className="idea" {...rise(i * 0.5)} onClick={() => { setQuery(x.q); search(x.q) }}>
                <small>{x.note}</small><span>{x.q}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </motion.button>
            ))}
          </div>
        </>
      )}

      {res && !loading && stats && (
        <>
          <motion.p className="dispatch" {...rise(0)} style={{ marginTop: 26 }}>{res.r.summary}</motion.p>
          <motion.div className="statchips" {...rise(1)}>
            <span><b className="num">{res.r.total_matching_filters.toLocaleString()}</b> cases match your filters</span>
            <span>found in <b className="num">{res.r.latency_ms} ms</b></span>
            {res.r.classification && <span>detected <b>{res.r.classification.disruption_type}</b></span>}
          </motion.div>

          <div className="glance2">
            <motion.div className="gl-tiles" {...rise(2)}>
              <div><small>Most common response</small><b>{stats.top[0]}</b><span>{stats.top[1]} of {res.r.results.length} cases</span></div>
              <div><small>Typical recovery</small><b className="num">{Math.round(stats.recovery)} days</b><span>fastest {stats.fastest.full_recovery_days} days</span></div>
              <div><small>Typical production hit</small><b className="num">{Math.round(stats.impact)}%</b><span>median of these cases</span></div>
              <div><small>Changed supplier for good</small><b className="num">{pct(stats.switched)}</b><span>of these cases</span></div>
            </motion.div>
            <motion.section className="card" {...rise(3)}><h4>How they were handled</h4>
              <Donut centre={String(res.r.results.length)} sub="cases" parts={stats.mix.map(([k, v]) => ({ label: k, value: v, color: RESP_HUE[k] ?? '#8ba3b3' }))} /></motion.section>
            <motion.section className="card" {...rise(4)}><h4>Recovery against damage</h4>
              <p className="muted blurb" style={{ marginBottom: 6 }}>Each dot is a case, numbered by match. Lower left is the best place to be.</p>
              <Scatter xLabel="Days to full recovery" yLabel="Production impact" dots={res.r.results.map((h, i) => ({ id: h.disruption_id, x: h.full_recovery_days, y: h.production_impact_pct, color: RESP_HUE[h.response_type] ?? '#8ba3b3', label: String(i + 1), tip: `${h.disruption_id} · ${h.response_type}: ${h.full_recovery_days} days, ${h.production_impact_pct.toFixed(0)}% impact, ${money(h.revenue_loss_usd)} lost` }))} /></motion.section>
          </div>

          <div className="sortbar"><span className="muted">{hits.length} cases, ordered by</span><Segmented label="Sort" value={sort} options={SORTS} onChange={setSort} /></div>
          <div className="cases">
            {hits.map((h, i) => (
              <CaseFile key={h.disruption_id + sort} h={h} i={i} query={res.q} maxDays={maxDays} maxImpact={maxImpact} fastest={h.disruption_id === stats.fastest.disruption_id}
                open={open.has(h.disruption_id)} toggle={() => setOpen((s) => { const n = new Set(s); if (n.has(h.disruption_id)) n.delete(h.disruption_id); else n.add(h.disruption_id); return n })} />
            ))}
          </div>
        </>
      )}
      {res && !loading && !stats && <Empty title="No matching disruptions">Remove a filter or rephrase the search.</Empty>}

      <SearchQuality />
    </div>
  )
}
