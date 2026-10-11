import { motion } from 'motion/react'
import type { Analysis, Contribution } from '../api'
import { money, pct, tidy } from '../lib'
import { Diverging, StackBar } from './charts'
import { Pips, RespChip } from './bits'
import { DeepCheck } from './DeepCheck'
import { EvidencePanel } from './Evidence'

const ease = [0.22, 0.8, 0.24, 1] as const

const stagger = (i: number) => ({ initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.45, delay: i * 0.07, ease } })
// ---------------------------------------------------------------- plan
export function PlanTab({ a }: { a: Analysis }) {
  const plan = a.response.plan
  return (
    <>
      <motion.section className="why" {...stagger(0)}>
        <div className="why-head">
          <h3>Why {plan.recommended_strategy}</h3>
          <span className="tag soft">Written by {plan.generated_by ?? 'the system'}</span>
        </div>
        <p>{plan.rationale}</p>
        {plan.cited_cases && plan.cited_cases.length > 0 && <p className="cited">Cases cited: {plan.cited_cases.join(', ')}</p>}
      </motion.section>
      {plan.evidence_note && <div className="notice warn"><div>{plan.evidence_note}</div></div>}
      {plan.minor_event_note && <div className="notice"><div><b>Minor event.</b> {plan.minor_event_note}</div></div>}
      {plan.close_call && <div className="notice"><div>{plan.close_call}</div></div>}

      <div className="trio">
        <motion.section className="step-card now" {...stagger(1)}>
          <h4><span className="h-icon"><svg viewBox="0 0 24 24"><path d="M13 3L5 13h6l-1 8 8-10h-6z" /></svg></span>Do now</h4>
          <ol className="steps">{plan.immediate_actions.map((x) => <li key={x}>{x}</li>)}</ol>
        </motion.section>
        <motion.section className="step-card later" {...stagger(2)}>
          <h4><span className="h-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" /><path d="M12 7.5V12l3 2" /></svg></span>Recovery plan</h4>
          <ul className="timeline">{plan.recovery_plan.map((x) => <li key={x}>{x}</li>)}</ul>
        </motion.section>
        <motion.section className="step-card risk" {...stagger(3)}>
          <h4><span className="h-icon"><svg viewBox="0 0 24 24"><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17v.5" /></svg></span>Risks to watch</h4>
          <ul className="bullets risk">{plan.risks.map((x) => <li key={x}>{x}</li>)}</ul>
        </motion.section>
      </div>

      <p className="footnote">
        The scoring system chooses the strategy (similar-case outcomes, predictions and feedback); the AI only explains it.
        {plan.guardrail_note && <> Output guardrail: {plan.guardrail_note}</>}
      </p>
      {plan.fact_sheet && (
        <details className="fold">
          <summary>Evidence the AI was given</summary>
          <div className="fold-body"><EvidencePanel a={a} /></div>
        </details>
      )}
    </>
  )
}

// ---------------------------------------------------------------- cases
const FILTER_LABELS: Record<string, string> = { disruption_type: 'type', industry: 'industry', supplier_region: 'region', supplier_tier: 'tier', response_type: 'response' }

export function CasesTab({ a }: { a: Analysis }) {
  const inv = a.investigation
  const f = inv.filters_applied as Record<string, unknown>
  const chips = Object.entries(f).filter(([k]) => !k.endsWith('_severity')).map(([k, v]) => [FILTER_LABELS[k] ?? k.replace(/_/g, ' '), Array.isArray(v) ? v.join(', ') : String(v)])
  if (f.min_severity != null || f.max_severity != null) chips.push(['severity', `${f.min_severity ?? 1}–${f.max_severity ?? 5}`])
  const worst = Math.max(...inv.similar_cases.map((c) => c.production_impact_pct), 1)
  return (
    <>
      <p className="prose" style={{ marginTop: 0 }}>{inv.historical_summary}</p>
      <div className="filterchips">{chips.map(([k, v]) => <span key={k}><i>{k}</i>{v}</span>)}</div>
      <p className="footnote" style={{ marginTop: 0, marginBottom: 16 }}>
        {inv.total_matching_filters.toLocaleString()} matching records; the closest are shown below.{inv.relaxations.length > 0 && ` ${inv.relaxations.join('; ')}`}
      </p>
      {inv.similar_cases.length === 0 ? (
        <div className="notice"><div>No matching disruptions. Widen the details or rephrase the description.</div></div>
      ) : (
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>Case</th><th>Response</th><th>Severity</th><th>Production impact</th><th className="r">Revenue loss</th><th className="r">Recovery</th><th>Switched supplier</th><th>Match</th>
            </tr></thead>
            <tbody>
              {inv.similar_cases.map((c, i) => (
                <motion.tr key={c.disruption_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: i * 0.035 }}>
                  <td><b className="cid">{c.disruption_id}</b><span className="sub">{c.disruption_type} · {c.industry} · {c.supplier_region}, tier {c.supplier_tier}</span></td>
                  <td><RespChip r={c.response_type} /></td>
                  <td><Pips n={c.disruption_severity} /></td>
                  <td><span className="inline-bar"><i style={{ width: `${(100 * c.production_impact_pct) / worst}%` }} /></span><span className="num">{c.production_impact_pct.toFixed(0)}%</span></td>
                  <td className="r num">{money(c.revenue_loss_usd)}</td>
                  <td className="r num">{c.full_recovery_days} days</td>
                  <td>{c.permanent_supplier_change ? 'Yes' : 'No'}</td>
                  <td>{c.hybrid_score != null && <span className="match" title={c.hybrid_score.toFixed(2)}><i style={{ width: `${Math.min(c.hybrid_score, 1) * 100}%` }} /></span>}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------- ranking
export function RankingTab({ a }: { a: Analysis }) {
  const ranking = a.response.strategy_ranking
  const recommended = a.response.plan.recommended_strategy || ranking[0]?.response_type
  const top = Math.max(...ranking.map((r) => r.strategy_score), 1)
  return (
    <>
      {a.response.basis && (
        <p className="footnote" style={{ marginTop: 0, marginBottom: 16 }}>
          Strategies are compared on {a.response.basis.description}. The cases in "Similar cases" are the closest examples from that group.
        </p>
      )}
      <div className="ranking">
        {ranking.map((r, i) => {
          const best = r.response_type === recommended
          return (
            <motion.div key={r.response_type} className={`rankrow ${best ? 'top' : ''}`}
              initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.45, delay: i * 0.07, ease }}>
              <span className="n num">{r.rank}</span>
              <div className="what">
                <b>{r.response_type}{best && <span className="tag">Recommended</span>}</b>
                <span>{r.evidence_cases ? `used in ${r.evidence_cases} of ${r.evidence_total} similar cases` : 'no similar case used it; model estimate only'}</span>
                {r.feasible_now === false && r.feasibility_note && <span className="infeasible">{r.feasibility_note}</span>}
              </div>
              <div className="score">
                <div className="meter"><motion.i style={{ width: `${(100 * r.strategy_score) / top}%` }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.9, delay: 0.2 + i * 0.07, ease }} /></div>
                <span>score {Math.round(r.strategy_score)}</span>
              </div>
              <div className="stat"><b className="num">{Math.round(r.expected_full_recovery_days)} days</b><span>full recovery</span></div>
              <div className="stat"><b className="num">{money(r.expected_revenue_loss_usd)}</b><span>revenue loss</span></div>
              <div className="stat"><b className="num">{pct(r.supplier_change_risk)}</b><span>supplier change</span></div>
            </motion.div>
          )
        })}
      </div>
    </>
  )
}

// ---------------------------------------------------------------- recovery
export function RecoveryTab({ a }: { a: Analysis }) {
  const rec = a.recovery
  const ms = [...rec.milestones].sort((x, y) => x.day - y.day)
  const last = Math.max(...ms.map((m) => m.day), 1)
  const rs = rec.resilience
  const tone = rs.resilience_score < 45 ? 'rust' : rs.resilience_score >= 75 ? 'sea' : ''
  return (
    <>
      <section className="card">
        <h4>Road to recovery</h4>
        <div className="track">
          <div className="line"><motion.i initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 1.2, ease }} /></div>
          {ms.map((m, i) => (
            <motion.div key={m.day + m.milestone} className={`mstone ${i % 2 === 0 ? 'up' : 'down'} ${i === 0 ? 'first' : ''} ${i === ms.length - 1 ? 'last' : ''}`}
              style={{ left: `${(100 * m.day) / last}%` }} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.3 + i * 0.14 }}>
              <span className="dot2" /><span className="lbl"><b className="num">Day {Math.round(m.day)}</b>{m.milestone}</span>
            </motion.div>
          ))}
        </div>
      </section>
      <div className="duo">
        <motion.section className="card stat-card" {...stagger(1)}>
          <span className="muted">Chance you'll switch supplier</span>
          <b className="big num">{pct(rec.supplier_change_probability)}</b>
          <p>{rec.supplier_change_outlook}</p>
        </motion.section>
        <motion.section className="card stat-card" {...stagger(2)}>
          <span className="muted">Supplier resilience</span>
          <b className={`big num ${tone}`}>{rs.resilience_score}<small>/100</small> <em>{rs.resilience_grade}</em></b>
          <p>Risk band: {rs.risk_band}</p>
        </motion.section>
      </div>
      <h3 className="subhead">Keep an eye on</h3>
      <div className="pills">{rec.monitoring_kpis.map((k, i) => <motion.span key={k} {...stagger(i * 0.4)}>{k}</motion.span>)}</div>
    </>
  )
}

// ---------------------------------------------------------------- impact drivers (diverging bars, no chart library)
function DriverCard({ title, blurb, unit, data, summary, i }: { title: string; blurb: string; unit: string; data: Contribution[]; summary: string; i: number }) {
  return (
    <motion.section className="card driver" {...stagger(i)}>
      <h4>{title}</h4>
      <p className="muted blurb">{blurb}</p>
      <div className="dlegend"><span><i className="up" />Pushes it up</span><span><i className="down" />Pulls it down</span></div>
      <Diverging rows={data} unit={unit} />
      <p className="dsummary">{summary}</p>
    </motion.section>
  )
}

const FACTOR_COLORS = ['#14506b', '#1d7a9e', '#5fb0cf', '#f2a900', '#c2452d', '#8ba3b3']

export function DriversTab({ a }: { a: Analysis }) {
  const d = a.impact_assessment.drivers
  const pr = a.impact_assessment.priority
  const factors = Object.entries(pr.factor_contributions).map(([k, v]) => ({ label: k.replace(/_/g, ' '), value: v })).sort((x, y) => y.value - x.value)
  return (
    <>
      <div className="duo">
        <DriverCard i={0} title="What drives recovery time" blurb="How much each factor adds to or takes off the expected recovery time." unit={d.full_recovery_days.unit}
          data={d.full_recovery_days.top} summary={d.full_recovery_days.summary} />
        <DriverCard i={1} title="What drives production impact" blurb="How much each factor adds to or takes off the expected production loss." unit={d.production_impact_pct.unit}
          data={d.production_impact_pct.top} summary={d.production_impact_pct.summary} />
      </div>
      <motion.section className="card" style={{ marginTop: 18 }} {...stagger(2)}>
        <div className="why-head"><h4 style={{ margin: 0 }}>How the priority score adds up</h4><span className="tag soft num">{Math.round(pr.priority_score)} points</span></div>
        <div style={{ height: 14 }} />
        <StackBar parts={factors.map((f, i) => ({ label: f.label, value: f.value, color: FACTOR_COLORS[i % FACTOR_COLORS.length] }))} />
      </motion.section>
    </>
  )
}

// ---------------------------------------------------------------- judge
export function JudgeTab({ a }: { a: Analysis }) {
  const j = a.judgement
  return (
    <>
      <motion.section className={`verdict-card ${j.passed ? 'pass' : 'fail'}`} {...stagger(0)}>
        <b className="num">{j.overall_score.toFixed(1)}<small>/5</small></b>
        <div><h4>{j.passed ? 'Passed the quick check' : 'Did not pass the quick check'}</h4>
          <p>Pass mark {j.threshold}. Checked by {j.judge === 'heuristic' ? 'a rule checklist, not a language model' : j.judge}. Revisions made: {a.revisions}.</p></div>
      </motion.section>
      {j.judge === 'heuristic' && <div className="notice warn"><div><b>This score came from a checklist, not an LLM judge.</b> {j.fallback_reason ? `Reason: ${j.fallback_reason}.` : ''} Pick a working model and run the analysis again for a model-based judgement.</div></div>}
      {j.overall_feedback && <div className="notice"><div>{j.overall_feedback}</div></div>}
      <p className="qc-note">This is a quick automated check, scored by the same kind of AI that wrote the plan, so it can be generous. For an independent assessment of this answer, run the deep check below.</p>
      <div className="criteria">
        {Object.entries(j.scores).map(([k, v], i) => (
          <motion.div key={k} className="crit" {...stagger(i + 1)}>
            <div className="crit-head"><b>{k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())}</b><Pips n={v} /><span className="num">{v}/5</span></div>
            {j.reasons[k] && <p>{j.reasons[k]}</p>}
          </motion.div>
        ))}
      </div>
      <DeepCheck query={a.query} plan={a.response.plan} />
    </>
  )
}

// ---------------------------------------------------------------- trace
export function TraceTab({ a }: { a: Analysis }) {
  const longest = Math.max(...a.trace.map((s) => s.duration_ms), 1)
  return (
    <>
      <ol className="trace">
        {a.trace.map((s, i) => (
          <motion.li key={s.agent + i} className={s.status === 'blocked' ? 'blocked' : ''} {...stagger(i * 0.6)}>
            <div className="trace-head"><span className="agent">{s.agent}</span><span className="ms num">{s.duration_ms >= 1000 ? `${(s.duration_ms / 1000).toFixed(1)}s` : `${s.duration_ms} ms`}</span></div>
            <span className="trace-bar"><i style={{ width: `${Math.max((100 * s.duration_ms) / longest, 1.5)}%` }} /></span>
            <p>{tidy(s.summary)}</p>
          </motion.li>
        ))}
      </ol>
      <p className="footnote">Total: {(a.total_duration_ms / 1000).toFixed(1)}s.</p>
    </>
  )
}
