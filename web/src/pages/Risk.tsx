import { motion } from 'motion/react'
import { useState } from 'react'
import { api, ApiError, type RiskResponse } from '../api'
import { Diverging, Gauge, HBars, Radar } from '../components/charts'
import { Empty, PageHead, Segmented, SelectField, Skeleton, Slider, Toggle } from '../components/ui'
import { ease, rise } from '../components/motionkit'
import { driverToPoints, INDUSTRIES, pct, REGIONS, SIZES } from '../lib'

// zones follow the backend's own cut-offs: resilience grades D<45, C<60, B<75, A; risk bands Low<20%, Moderate<40%, High<60%, Very High
const RESILIENCE_ZONES = [
  { upTo: 45, color: '#c2452d', tint: 'color-mix(in srgb, #c2452d 24%, var(--surface))' }, { upTo: 60, color: '#d9711c', tint: 'color-mix(in srgb, #d9711c 24%, var(--surface))' },
  { upTo: 75, color: '#b08a00', tint: 'color-mix(in srgb, #b08a00 24%, var(--surface))' }, { upTo: 100, color: '#2e7d5b', tint: 'color-mix(in srgb, #2e7d5b 24%, var(--surface))' },
]
const RISK_ZONES = [
  { upTo: 20, color: '#2e7d5b', tint: 'color-mix(in srgb, #2e7d5b 24%, var(--surface))' }, { upTo: 40, color: '#b08a00', tint: 'color-mix(in srgb, #b08a00 24%, var(--surface))' },
  { upTo: 60, color: '#d9711c', tint: 'color-mix(in srgb, #d9711c 24%, var(--surface))' }, { upTo: 100, color: '#c2452d', tint: 'color-mix(in srgb, #c2452d 24%, var(--surface))' },
]

export function Risk() {
  const [f, setF] = useState({ industry: 'Electronics', region: 'Asia-Pacific', tier: '1', size: 'Medium' })
  const [severity, setSeverity] = useState(3)
  const [backup, setBackup] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [r, setR] = useState<RiskResponse | null>(null)
  const [view, setView] = useState<'chosen' | 'typical'>('chosen')
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }))

  const run = async () => {
    setLoading(true); setError(null)
    try {
      setR(await api.risk({ industry: f.industry, supplier_region: f.region, supplier_tier: Number(f.tier), supplier_size: f.size, has_backup_supplier: backup, assumed_severity: severity }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Scoring failed. Try again.')
    } finally { setLoading(false) }
  }

  const score = (e: RiskResponse['exposure_by_type'][number]) => (view === 'typical' ? e.vulnerability_at_typical_severity : e.vulnerability)
  const vs = r ? r.exposure_by_type.map(score) : [0]
  const gap = Math.round(100 * (Math.max(...vs) - Math.min(...vs)))
  const byVuln = r ? [...r.exposure_by_type].sort((a, b) => score(b) - score(a)) : []

  return (
    <div className="wrap page-body">
      <PageHead title="Score a supplier's resilience" lede="How well would this supplier absorb a disruption, and how likely is one to turn high-impact? Every disruption type is weighed by how often it has happened." />

      <motion.section className="panel formcard" {...rise(1)}>
        <div className="formgrid">
          <SelectField label="Industry" value={f.industry} options={INDUSTRIES} onChange={set('industry')} />
          <SelectField label="Region" value={f.region} options={REGIONS} onChange={set('region')} />
          <SelectField label="Tier" value={f.tier} options={[1, 2, 3, 4]} onChange={set('tier')} />
          <SelectField label="Size" value={f.size} options={SIZES} onChange={set('size')} />
          <Slider label="Assumed severity" value={severity} min={1} max={5} onChange={setSeverity} />
          <Toggle label="Backup supplier available" checked={backup} onChange={setBackup} />
        </div>
        <div className="formfoot"><span className="spacer" /><button className="btn" onClick={run} disabled={loading}>{loading ? 'Scoring' : 'Score resilience'}</button></div>
      </motion.section>

      {loading && <div className="stackgap"><Skeleton h={220} /><Skeleton h={300} /></div>}
      {error && !loading && <div className="notice error" role="alert"><div><b>Scoring failed.</b> {error}</div></div>}
      {!r && !loading && !error && <Empty title="Describe the supplier">Pick an industry, region and tier, then score it to see its resilience and where it is most exposed.</Empty>}

      {r && !loading && (
        <>
          <div className="duo" style={{ marginTop: 26 }}>
            <motion.section className="card center" {...rise(0)}>
              <h4>Resilience</h4>
              <Gauge value={r.resilience_score} zones={RESILIENCE_ZONES} label={`Grade ${r.resilience_grade}`} sub="out of 100, higher is better" />
            </motion.section>
            <motion.section className="card center" {...rise(1)}>
              <h4>Chance a disruption turns high-impact</h4>
              <Gauge value={100 * r.disruption_risk_probability} zones={RISK_ZONES} label={r.risk_band} sub={`${pct(r.disruption_risk_probability)} chance, lower is better`} />
            </motion.section>
          </div>

          <div className="duo">
            <motion.section className="card" {...rise(2)}>
              <div className="why-head"><h4 style={{ margin: 0 }}>Where this supplier is exposed</h4>
                <Segmented label="Severity used" value={view} onChange={setView} options={[{ id: 'chosen', label: `At severity ${severity}` }, { id: 'typical', label: 'At typical severity' }]} /></div>
              <p className="muted blurb">{view === 'chosen'
                ? `Every type is tested at the same severity (${severity}), so the shape is nearly round: the six types differ by only ${gap} points, because severity, backup supplier and tier move the outcome far more than the type of disruption does.`
                : `Every type is tested at the severity it usually has in the historical record (for example cyber attacks are usually more severe than port congestion), so the types differ by ${gap} points. That is the real difference between them.`}
                {' '}Fixed scale: the centre is no vulnerability, the outer ring is fully vulnerable.</p>
              <Radar axes={r.exposure_by_type.map((e) => ({ label: e.disruption_type, value: Math.max(score(e), 0.02), detail: `${pct(e.historical_frequency)} of past cases` }))} />
            </motion.section>
            <motion.section className="card" {...rise(3)}>
              <h4>Exposure by disruption type</h4>
              <p className="muted blurb">Most vulnerable first, on a 0 to 1 scale, with how often it happened, how severe it usually is and how long recovery takes.</p>
              <HBars max={1} rows={byVuln.map((e) => ({
                label: e.disruption_type, value: score(e), color: score(e) >= 0.55 ? '#c2452d' : score(e) >= 0.25 ? '#d99a00' : '#1d7a9e',
                sub: `${pct(e.historical_frequency)} of cases · typical severity ${e.typical_severity.toFixed(1)} · ${Math.round(e.predicted_full_recovery_days)} days to recover`,
              }))} format={(v) => v.toFixed(2)} />
            </motion.section>
          </div>

          <motion.section className="card" style={{ marginTop: 16 }} {...rise(4)}>
            <h4>What would you do about it?</h4>
            <div className="recs">
              {r.recommendations.map((t, i) => (
                <motion.div key={t} className="rec" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.25 + i * 0.08, ease }}>
                  <span className="num">{i + 1}</span><p>{t}</p>
                </motion.div>
              ))}
            </div>
          </motion.section>

          <motion.section className="card" style={{ marginTop: 16 }} {...rise(5)}>
            <h4>What raises or lowers the risk</h4>
            <div className="dlegend"><span><i className="up" />Raises the risk</span><span><i className="down" />Lowers the risk</span></div>
            <Diverging rows={driverToPoints(r.disruption_risk_probability, r.top_risk_drivers)} unit="pts" />
            <p className="footnote">Each bar is the approximate change, in percentage points, to the {pct(r.disruption_risk_probability)} chance of a high-impact disruption.</p>
          </motion.section>
        </>
      )}
    </div>
  )
}
