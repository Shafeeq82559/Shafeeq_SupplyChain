import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { api, type Insights as InsightsData, type Stats } from '../api'
import { HBars, Heatmap, LineChart } from '../components/charts'
import { Kpi } from '../components/Kpi'
import { PageHead, Segmented, Skeleton } from '../components/ui'
import { ease, rise } from '../components/motionkit'
import { money, pct, RESPONSES } from '../lib'

const TARGET_LABELS: Record<string, string> = {
  production_impact_pct: 'Production impact', revenue_loss_usd: 'Revenue loss', full_recovery_days: 'Full recovery', partial_recovery_days: 'Partial recovery',
  high_impact: 'High impact', permanent_supplier_change: 'Supplier change',
}
/** One key-finding sentence ("X is a key driver of Y (explains N% of variance, p<..): A averages a vs B b.") as a compact card. */
const FINDING = /^(.+?) is a key driver of (.+?) \(explains ([\d.]+)% of variance, (p[<=][\d.]+)\): (.+?) averages (\$[\d,.]+M|[\d,.]+%|[\d,.]+ days) vs (.+) (\$[\d,.]+M|[\d,.]+%|[\d,.]+ days)\.$/
const num = (v: string) => parseFloat(v.replace(/[^\d.]/g, ''))

function Finding({ line, i }: { line: string; i: number }) {
  const m = FINDING.exec(line)
  const anim = { initial: { opacity: 0, y: 14 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true }, transition: { duration: 0.45, delay: (i % 3) * 0.07, ease } }
  if (!m && line.startsWith('Note:')) return <motion.div className="finding note" {...anim}><span>!</span><p><b>Heads up.</b> {line.slice(5).trim()}</p></motion.div>
  if (!m) return <motion.div className="finding" {...anim}><span className="num">{i + 1}</span><p>{line}</p></motion.div>
  const [, factor, outcome, share, p, hiName, hiVal, loName, loVal] = m
  const top = Math.max(num(hiVal), num(loVal), 1e-9)
  return (
    <motion.article className="fcard" {...anim}>
      <header><b>{factor}</b><span>drives {outcome.replace(/ %$/, '')}</span></header>
      <div className="fshare"><b className="num">{share}%</b><span>of the variation it explains<small title="Probability the difference is down to chance">{p}</small></span></div>
      <div className="fgroups">
        <div><span>{hiName}</span><i className="hi" style={{ width: `${(100 * num(hiVal)) / top}%` }} /><b className="num">{hiVal}</b></div>
        <div><span>{loName}</span><i className="lo" style={{ width: `${(100 * num(loVal)) / top}%` }} /><b className="num">{loVal}</b></div>
      </div>
    </motion.article>
  )
}

interface Loaded { s: Stats; ins: InsightsData }

export function Insights() {
  const [d, setD] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [target, setTarget] = useState('full_recovery_days')

  useEffect(() => {
    let live = true
    Promise.all([api.stats(), api.insights()])
      .then(([s, ins]) => { if (live) setD({ s, ins }) })
      .catch((e: Error) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [])

  if (error) return <div className="wrap page-body"><div className="notice error" role="alert"><div><b>Couldn't load the insights.</b> {error}</div></div></div>
  if (!d) return (
    <div className="wrap page-body"><PageHead title="What the past disruptions show" lede="Patterns across the historical record: what hurts most, what speeds recovery, and what drives the outcomes." />
      <div className="stackgap"><Skeleton h={110} /><Skeleton h={280} /><Skeleton h={280} /></div></div>
  )

  const { s, ins } = d
  const t = s.totals
  const sev = Object.entries(s.by_severity).sort(([a], [b]) => Number(a) - Number(b))
  const types = Object.entries(s.by_disruption_type).sort(([, a], [, b]) => b.avg_full_recovery_days - a.avg_full_recovery_days)
  const industries = Object.entries(s.by_industry).sort(([, a], [, b]) => b.avg_production_impact_pct - a.avg_production_impact_pct)
  const heatRows = Object.keys(s.recovery_days_by_type_and_response)
  const heatCols = RESPONSES.filter((r) => heatRows.some((row) => s.recovery_days_by_type_and_response[row]?.[r] != null))
  const imp = ins.global_importance[target] ?? []

  return (
    <div className="wrap page-body">
      <PageHead title={`What ${s.total_records.toLocaleString()} past disruptions show`} lede="Patterns across the historical record: what hurts most, what speeds recovery, and what drives the outcomes." />

      <div className="kpis">
        <Kpi i={0} icon="db" label="Disruptions on record" value={s.total_records} format={(v) => Math.round(v).toLocaleString()} />
        <Kpi i={1} icon="gauge" label="Average production impact" value={t.avg_production_impact_pct} format={(v) => `${v.toFixed(1)}%`} />
        <Kpi i={2} icon="clock" label="Median full recovery" value={t.median_full_recovery_days} format={(v) => `${Math.round(v)} days`} />
        <Kpi i={3} icon="shield" label="Had a backup supplier" value={100 * t.backup_supplier_rate} format={(v) => `${Math.round(v)}%`} meter={t.backup_supplier_rate} />
        <Kpi i={4} icon="swap" label="Switched supplier for good" value={100 * t.permanent_supplier_change_rate} format={(v) => `${Math.round(v)}%`} meter={t.permanent_supplier_change_rate} />
      </div>

      <h3 className="subhead big">Key findings</h3>
      <div className="findings">
        {ins.key_insights.map((line, i) => <Finding key={line} line={line} i={i} />)}
      </div>

      <h3 className="subhead big">How severity changes the damage</h3>
      <div className="duo">
        <motion.section className="card" {...rise(0)}><h4>Production impact by severity</h4>
          <LineChart points={sev.map(([k, v]) => ({ x: k, y: v.avg_production_impact_pct }))} color="#c2452d" format={(v) => `${Math.round(v)}%`} xLabel="Severity" /></motion.section>
        <motion.section className="card" {...rise(1)}><h4>Days to full recovery by severity</h4>
          <LineChart points={sev.map(([k, v]) => ({ x: k, y: v.avg_full_recovery_days }))} color="#14506b" format={(v) => `${Math.round(v)}`} xLabel="Severity" /></motion.section>
      </div>

      <h3 className="subhead big">Which disruptions hurt most</h3>
      <div className="duo">
        <section className="card"><h4>Average days to full recovery, by type</h4>
          <HBars rows={types.map(([k, v]) => ({ label: k, value: v.avg_full_recovery_days, sub: `${v.count.toLocaleString()} cases · ${money(v.avg_revenue_loss_usd)} average loss`, color: '#1d7a9e' }))} format={(v) => `${Math.round(v)} days`} /></section>
        <section className="card"><h4>Average production impact, by industry</h4>
          <HBars rows={industries.map(([k, v]) => ({ label: k, value: v.avg_production_impact_pct, sub: `${v.count.toLocaleString()} cases · ${pct(v.supplier_change_rate)} switched supplier`, color: '#c2452d' }))} format={(v) => `${v.toFixed(1)}%`} /></section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h4>Average days to full recovery, by disruption type and response</h4>
        <p className="muted blurb">Greener is faster. A strategy that wins for one type can lose for another.</p>
        <Heatmap rows={heatRows} cols={heatCols} data={s.recovery_days_by_type_and_response} />
      </section>

      <h3 className="subhead big">What drives the outcomes</h3>
      <section className="card">
        <div className="why-head"><h4 style={{ margin: 0 }}>Share of influence, by factor</h4>
          <Segmented label="Outcome" value={target} onChange={setTarget} options={Object.keys(ins.global_importance).map((k) => ({ id: k, label: TARGET_LABELS[k] ?? k }))} /></div>
        <div style={{ height: 14 }} />
        <HBars key={target} rows={[...imp].sort((a, b) => b.share_pct - a.share_pct).map((x) => ({ label: x.label, value: x.share_pct }))} format={(v) => `${v.toFixed(1)}%`} />
      </section>

      <motion.a className="evalcta" href="#/evaluation" {...rise(0)}>
        <div><b>How well does the assistant itself score?</b><span>Search accuracy, answer quality, and the honest limits, with the reasons, on the Evaluation page.</span></div>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
      </motion.a>
    </div>
  )
}
