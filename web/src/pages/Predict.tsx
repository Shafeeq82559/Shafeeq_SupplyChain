import { motion } from 'motion/react'
import { useState } from 'react'
import { api, ApiError, type ExplainResponse, type PredictResponse } from '../api'
import { HBars, Waterfall } from '../components/charts'
import { Kpi } from '../components/Kpi'
import { Empty, PageHead, SelectField, Skeleton, Slider, Toggle } from '../components/ui'
import { rise } from '../components/motionkit'
import { INDUSTRIES, logOddsToPoints, money, pct, REGIONS, RESPONSES, SIZES, TYPES } from '../lib'

const TARGETS: Record<string, string> = {
  full_recovery_days: 'Full recovery time', production_impact_pct: 'Production impact', revenue_loss_usd: 'Revenue loss',
  partial_recovery_days: 'Partial recovery time', high_impact: 'Chance of high impact', permanent_supplier_change: 'Chance of switching supplier',
}

export function Predict() {
  const [f, setF] = useState({ type: 'Natural Disaster', industry: 'Electronics', region: 'Asia-Pacific', tier: '1', size: 'Medium', response: 'Alternative Supplier' })
  const [severity, setSeverity] = useState(4)
  const [backup, setBackup] = useState(false)
  const [target, setTarget] = useState('full_recovery_days')
  const [narrate, setNarrate] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [out, setOut] = useState<{ p: PredictResponse; e: ExplainResponse; response: string; target: string } | null>(null)
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }))

  const run = async () => {
    setLoading(true); setError(null)
    const profile = {
      disruption_type: f.type, industry: f.industry, supplier_region: f.region, supplier_tier: Number(f.tier), supplier_size: f.size,
      has_backup_supplier: backup, disruption_severity: severity, response_type: f.response,
    }
    try {
      const [p, e] = await Promise.all([api.predict(profile), api.explain(profile, target, narrate)])
      setOut({ p, e, response: f.response, target })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Prediction failed. Try again.')
    } finally { setLoading(false) }
  }

  const p = out?.p.predictions
  const whatIf = out ? [...out.p.what_if_by_response].sort((a, b) => a.predicted_full_recovery_days - b.predicted_full_recovery_days) : []
  const best = whatIf[0]?.response_type
  const yesNo = !!out && /log-odds/i.test(out.e.unit)
  const wf = out && yesNo ? logOddsToPoints(out.e.baseline, out.e.prediction, out.e.contributions) : null
  const wfSummary = wf && out ? `${TARGETS[out.target]} is about ${wf.prediction.toFixed(0)}% for this case, against ${wf.baseline.toFixed(0)}% for a typical past case. The biggest effects: ${wf.rows.slice(0, 3).map((r) => `${r.label} = ${r.value} (${r.contribution > 0 ? '+' : '−'}${Math.abs(r.contribution).toFixed(0)} ${Math.abs(r.contribution).toFixed(0) === '1' ? 'pt' : 'pts'})`).join('; ')}.` : null

  return (
    <div className="wrap page-body">
      <PageHead title="Predict impact and explain it" lede="Estimate production impact, financial loss and recovery time for a disruption profile, compare response strategies, and see which factors move the numbers." />

      <motion.section className="panel formcard" {...rise(1)}>
        <div className="formgrid">
          <SelectField label="Disruption type" value={f.type} options={TYPES} onChange={set('type')} />
          <SelectField label="Industry" value={f.industry} options={INDUSTRIES} onChange={set('industry')} />
          <SelectField label="Supplier region" value={f.region} options={REGIONS} onChange={set('region')} />
          <SelectField label="Supplier tier" value={f.tier} options={[1, 2, 3, 4]} onChange={set('tier')} />
          <SelectField label="Supplier size" value={f.size} options={SIZES} onChange={set('size')} />
          <SelectField label="Response strategy" value={f.response} options={RESPONSES} onChange={set('response')} />
          <Slider label="Severity" value={severity} min={1} max={5} onChange={setSeverity} />
          <Toggle label="Backup supplier available" checked={backup} onChange={setBackup} />
        </div>
        <div className="formfoot">
          <label className="field inline">Explain this prediction
            <select value={target} onChange={(e) => setTarget(e.target.value)}>{Object.entries(TARGETS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </label>
          <Toggle label="Add a plain-language explanation" hint="uses the language model" checked={narrate} onChange={setNarrate} />
          <span className="spacer" />
          <button className="btn" onClick={run} disabled={loading}>{loading ? 'Predicting' : 'Predict and explain'}</button>
        </div>
      </motion.section>

      {loading && <div className="stackgap"><Skeleton h={120} /><Skeleton h={260} /></div>}
      {error && !loading && <div className="notice error" role="alert"><div><b>Prediction failed.</b> {error}</div></div>}
      {!out && !loading && !error && <Empty title="Set up a disruption profile">Choose the details above and press Predict. You'll get estimates with likely ranges, a what-if for each strategy, and the factors behind the numbers.</Empty>}

      {out && p && !loading && (
        <>
          <div className="kpis" style={{ marginTop: 26 }}>
            <Kpi i={0} icon="gauge" label="Production impact" range={p.production_impact_pct} format={(v) => `${v.toFixed(1)}%`} max={100} note={`likely ${p.production_impact_pct.low_p10.toFixed(0)}–${p.production_impact_pct.high_p90.toFixed(0)}%`} />
            <Kpi i={1} icon="coin" label="Revenue loss" range={p.revenue_loss_usd} format={money} note={`likely ${money(p.revenue_loss_usd.low_p10)}–${money(p.revenue_loss_usd.high_p90)}`} />
            <Kpi i={2} icon="clock" label="Full recovery" range={p.full_recovery_days} format={(v) => `${Math.round(v)} days`} note={`likely ${Math.round(p.full_recovery_days.low_p10)}–${Math.round(p.full_recovery_days.high_p90)} days`} />
            <Kpi i={3} icon="bolt" label="Chance of high impact" value={100 * p.high_impact_probability} format={(v) => `${Math.round(v)}%`} tone={p.high_impact_probability >= 0.5 ? 'rust' : ''} meter={p.high_impact_probability} note="worst quarter of past cases" />
            <Kpi i={4} icon="swap" label="Chance of switching supplier" value={100 * p.supplier_change_probability} format={(v) => `${Math.round(v)}%`} meter={p.supplier_change_probability} note="permanent change" />
          </div>

          <div className="duo">
            <motion.section className="card" {...rise(2)}>
              <h4>What if you respond differently?</h4>
              <p className="muted blurb">Predicted days to full recovery for the same disruption. Your choice is outlined; the fastest is green.</p>
              <HBars rows={whatIf.map((w) => ({
                label: w.response_type, value: w.predicted_full_recovery_days, color: w.response_type === best ? '#2e7d5b' : w.response_type === out.response ? '#14506b' : '#9fb0bb',
                sub: `${money(w.predicted_revenue_loss_usd)} loss · ${pct(w.supplier_change_probability)} switch`,
              }))} highlight={out.response} format={(v) => `${Math.round(v)} days`} />
            </motion.section>
            <motion.section className="card" {...rise(3)}>
              <h4>Why: {TARGETS[out.target].toLowerCase()}</h4>
              <p className="muted blurb">Starts at the average past case and shows how each factor moves this estimate.</p>
              {yesNo && wf ? (
                <Waterfall baseline={wf.baseline} prediction={wf.prediction} unit="pts" totalUnit="%" rows={wf.rows} baseLabel="Typical case" endLabel="This case" />
              ) : (
                <Waterfall baseline={out.e.baseline} prediction={out.e.prediction} unit={out.e.unit} rows={out.e.contributions} />
              )}
            </motion.section>
          </div>
          <motion.p className="dispatch" {...rise(4)} style={{ marginTop: 18 }}>{out.e.narrative || wfSummary || out.e.summary}</motion.p>
        </>
      )}
    </div>
  )
}
