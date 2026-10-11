import type { Analysis, Range } from '../api'
import { money } from '../lib'
import { Pips, RespChip } from './bits'

interface Example { id: string; severity: number; kind: string; industry: string; impact: number; revenue: number; response: string; days: number }

/** The closest-example lines of the fact sheet ("- DIS-000123: severity 4 Cyber Attack, Electronics, production impact 31.2%, ..."). */
function examplesFrom(text: string): Example[] {
  const re = /^- (DIS-\d+): severity (\d) (.+?), (.+?), production impact ([\d.]+)%, revenue loss \$([\d.]+)M, response (.+?), full recovery (\d+) days/
  return text.split('\n').flatMap((line) => {
    const m = re.exec(line.trim())
    return m ? [{ id: m[1], severity: +m[2], kind: m[3], industry: m[4], impact: +m[5], revenue: +m[6] * 1e6, response: m[7], days: +m[8] }] : []
  })
}

function RangeBar({ label, r, max, fmt }: { label: string; r: Range; max: number; fmt: (v: number) => string }) {
  const at = (v: number) => `${Math.min(100, (100 * v) / max)}%`
  return (
    <div className="ev-range">
      <div className="ev-rtop"><span>{label}</span><b className="num">{fmt(r.predicted)}</b></div>
      <div className="range"><span className="band" style={{ left: at(r.low_p10), width: `calc(${at(r.high_p90)} - ${at(r.low_p10)})` }} /><span className="mark" style={{ left: at(r.predicted) }} /></div>
      <small>likely {fmt(r.low_p10)} to {fmt(r.high_p90)}</small>
    </div>
  )
}

export function EvidencePanel({ a }: { a: Analysis }) {
  const plan = a.response.plan, p = a.profile
  const ranking = a.response.strategy_ranking
  const pred = a.impact_assessment.predictions
  const examples = plan.fact_sheet ? examplesFrom(plan.fact_sheet) : []
  const slowest = Math.max(...ranking.map((r) => r.expected_full_recovery_days), 1)
  const worst = Math.max(...examples.map((e) => e.impact), 1)
  const cited = new Set(plan.cited_cases ?? [])

  return (
    <div className="ev">
      <div className="ev-chips">
        <span><i>type</i>{p.disruption_type}</span><span><i>severity</i><Pips n={p.disruption_severity} /></span>
        <span><i>supplier</i>Tier {p.supplier_tier} · {p.industry}</span><span><i>region</i>{p.supplier_region}</span>
        <span><i>backup</i>{p.has_backup_supplier ? 'yes' : 'none'}</span>
      </div>

      <div className="ev-duo">
        <section>
          <h5>Strategies compared <small>expected days to full recovery</small></h5>
          <div className="ev-strats">
            {ranking.map((r) => (
              <div key={r.response_type} className={`ev-strat ${r.response_type === plan.recommended_strategy ? 'chosen' : ''}`}>
                <div className="ev-stop"><span>{r.response_type}{r.response_type === plan.recommended_strategy && <em>chosen</em>}</span><b className="num">{Math.round(r.expected_full_recovery_days)} d</b></div>
                <span className="ev-track"><i style={{ width: `${(100 * r.expected_full_recovery_days) / slowest}%` }} /></span>
                <small>{r.evidence_cases ? `used in ${r.evidence_cases} of ${r.evidence_total} similar cases` : 'no similar case used it'} · {Math.round(100 * r.supplier_change_risk)}% chance of switching supplier</small>
              </div>
            ))}
          </div>
        </section>
        <section>
          <h5>Estimates for this disruption <small>dot is the estimate, band is the likely range</small></h5>
          <RangeBar label="Production impact" r={pred.production_impact_pct} max={100} fmt={(v) => `${v.toFixed(0)}%`} />
          <RangeBar label="Revenue loss" r={pred.revenue_loss_usd} max={pred.revenue_loss_usd.high_p90 * 1.1} fmt={money} />
        </section>
      </div>

      {examples.length > 0 && (
        <section>
          <h5>Closest past cases the AI saw <small>{cited.size ? 'cited cases are marked' : 'examples only'}</small></h5>
          <div className="ev-cases">
            {examples.map((e) => (
              <div key={e.id} className={`ev-case ${cited.has(e.id) ? 'cited' : ''}`}>
                <b className="cid">{e.id}</b>
                <span className="ev-what">{e.kind} · {e.industry}</span>
                <RespChip r={e.response} />
                <Pips n={e.severity} />
                <span className="ev-imp"><span className="inline-bar"><i style={{ width: `${(100 * e.impact) / worst}%` }} /></span><span className="num">{e.impact.toFixed(0)}%</span></span>
                <span className="num">{money(e.revenue)}</span>
                <span className="num">{e.days} d</span>
                {cited.has(e.id) && <em className="ev-cite">cited</em>}
              </div>
            ))}
          </div>
        </section>
      )}

      {plan.fact_sheet && (
        <details className="fold slim">
          <summary>Show the exact text sent to the AI</summary>
          <pre className="ev-raw">{plan.fact_sheet}</pre>
        </details>
      )}
    </div>
  )
}
