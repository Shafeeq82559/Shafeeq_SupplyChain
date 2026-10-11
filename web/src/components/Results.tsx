import { motion } from 'motion/react'
import { useId, useState } from 'react'
import type { Analysis, Overrides } from '../api'
import { money, PRIORITY_COLOR, useCountUp } from '../lib'
import { Feedback } from './Feedback'
import { Kpi } from './Kpi'
import { ReportMenu } from './ReportMenu'
import { CasesTab, DriversTab, JudgeTab, PlanTab, RankingTab, RecoveryTab, TraceTab } from './Tabs'

const OVERRIDE_LABELS: Record<string, string> = {
  disruption_type: 'Type', industry: 'Industry', supplier_region: 'Region', supplier_tier: 'Tier', supplier_size: 'Size',
  has_backup_supplier: 'Backup supplier', disruption_severity: 'Severity',
}
const TABS = ['Response plan', 'Similar cases', 'Strategy ranking', 'Recovery', 'Impact drivers', 'Quality check', 'Agent trace'] as const
type Tab = (typeof TABS)[number]
import { ease, rise } from './motionkit'

function Ring({ score, color }: { score: number; color: string }) {
  const r = 44, c = 2 * Math.PI * r
  const shown = useCountUp(score, 1100, 250)
  return (
    <div className="ring" role="img" aria-label={`Priority score ${Math.round(score)} out of 100`}>
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} className="ring-track" />
        <motion.circle cx="50" cy="50" r={r} className="ring-bar" stroke={color} strokeDasharray={c}
          initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - Math.min(score, 100) / 100) }} transition={{ duration: 1.2, delay: 0.25, ease }} />
      </svg>
      <span className="num">{Math.round(shown)}</span>
    </div>
  )
}

export function Results({ a, used }: { a: Analysis; used: Overrides }) {
  const [tab, setTab] = useState<Tab>('Response plan')
  const uid = useId()
  const { predictions: p, priority: pr } = a.impact_assessment
  const plan = a.response.plan
  const j = a.judgement
  const rec = a.recovery
  const simplified = plan.generated_by === 'template' || j.judge === 'heuristic' || a.classification.method === 'rules'
  const usedEntries = Object.entries(used)
  const color = PRIORITY_COLOR[pr.priority_level] ?? 'var(--muted)'
  // the summary is one long paragraph: lead with the first sentence, keep the rest one click away
  const cut = a.executive_summary.indexOf('Strategies were compared')
  const lead = (cut > 0 ? a.executive_summary.slice(0, cut) : a.executive_summary).trim()
  const more = cut > 0 ? a.executive_summary.slice(cut).trim() : ''
  const firstSentence = lead.split(/(?<=\.)\s+(?=[A-Z])/)[0]

  return (
    <div className="results">
      <ReportMenu a={a} used={used} />
      <motion.section className="brief" {...rise(0)}>
        <div className="brief-main">
          <Ring score={pr.priority_score} color={color} />
          <div>
            <span className="brief-tag" style={{ ['--c' as string]: color }}>{pr.priority_level} · {pr.priority_label}</span>
            <h2>{a.profile.disruption_type} in {a.profile.industry.toLowerCase()}, {a.profile.supplier_region}</h2>
            <p>{firstSentence}</p>
          </div>
        </div>
        <div className="brief-reco">
          <span className="reco-k">Recommended response</span>
          <b className="reco-name">{plan.recommended_strategy}</b>
          <div className="reco-facts">
            <span><b className="num">~{Math.round(rec.timeline.full_recovery_days.predicted)}</b> days to full recovery</span>
            <span><b className="num">~{Math.round(rec.timeline.partial_recovery_days.predicted)}</b> days to partial recovery</span>
          </div>
          {plan.fallback_strategy && <span className="reco-fb">Fallback: {plan.fallback_strategy}</span>}
        </div>
      </motion.section>

      {(lead.length > firstSentence.length || more) && (
        <details className="fold slim">
          <summary>Read the full summary</summary>
          <div className="fold-body"><p className="prose" style={{ marginTop: 0 }}>{lead.slice(firstSentence.length).trim()} {more}</p></div>
        </details>
      )}

      <div className="kpis">
        <Kpi i={1} icon="gauge" label="Production impact" range={p.production_impact_pct} format={(v) => `${v.toFixed(1)}%`} max={100}
          note={`likely ${p.production_impact_pct.low_p10.toFixed(0)}–${p.production_impact_pct.high_p90.toFixed(0)}%`} />
        <Kpi i={2} icon="coin" label="Revenue loss" range={p.revenue_loss_usd} format={money}
          note={`likely ${money(p.revenue_loss_usd.low_p10)}–${money(p.revenue_loss_usd.high_p90)}`} />
        <Kpi i={3} icon="clock" label="Full recovery" range={p.full_recovery_days} format={(v) => `${Math.round(v)} days`} bar={false}
          note={`likely ${Math.round(p.full_recovery_days.low_p10)}–${Math.round(p.full_recovery_days.high_p90)} days`} />
        <Kpi i={4} icon="bolt" label="Chance of high impact" value={100 * p.high_impact_probability} format={(v) => `${Math.round(v)}%`}
          tone={p.high_impact_probability >= 0.5 ? 'rust' : ''} note="worst quarter of past cases" meter={p.high_impact_probability} />
        <Kpi i={5} icon="check" label="Automated check" value={j.overall_score} format={(v) => `${v.toFixed(1)}/5`}
          tone={j.passed ? 'sea' : 'rust'} note={j.passed ? 'passed the quick check' : 'did not pass the quick check'} meter={j.overall_score / 5} />
      </div>
      <p className="footnote kpi-foot">Recovery days are the time similar past disruptions took to get back to normal operations, not the length of the outage itself. Even a short outage rarely recovers in under a few weeks in these records.</p>

      {(usedEntries.length > 0 || (a.assumptions && a.assumptions.length > 0) || (a.override_notes && a.override_notes.length > 0) || (a.ambiguity_notes && a.ambiguity_notes.length > 0) || simplified) && (
        <div className="notes">
          {usedEntries.length > 0 && <p>Using your details: {usedEntries.map(([k, v]) => `${OVERRIDE_LABELS[k]} = ${v === true ? 'Yes' : v === false ? 'No' : v}`).join(', ')}.</p>}
          {a.override_notes && a.override_notes.length > 0 && <div className="notice warn"><div><b>Please check:</b> {a.override_notes.join('; ')}. Your values were used as entered.</div></div>}
          {a.ambiguity_notes && a.ambiguity_notes.length > 0 && (
            <div className="notice warn"><div><b>The description is ambiguous.</b> {a.ambiguity_notes.map((n) => `${n}.`).join(' ')}</div></div>
          )}
          {a.assumptions && a.assumptions.length > 0 && <p>Assumed: {a.assumptions.join('; ')}.</p>}
          {simplified && (
            <div className="notice"><div><b>Simplified analysis.</b> The language model wasn't used for part of this result (it is switched off, unavailable, or gave an unusable answer).
              Keyword rules read the description, the plan comes from a template and the quality check is a checklist. Numbers, search and ranking are unchanged.</div></div>
          )}
        </div>
      )}

      <div className="pilltabs-wrap">
        <div className="pilltabs" role="tablist" aria-label="Analysis sections">
          {TABS.map((t) => (
            <button key={t} role="tab" id={`${uid}-${t}`} className="pilltab" aria-selected={tab === t} aria-controls={`${uid}-panel`} onClick={() => setTab(t)}>
              {tab === t && <motion.span layoutId={`${uid}-pill`} className="pilltab-bg" transition={{ type: 'spring', stiffness: 520, damping: 40 }} />}
              <span className="lbl">{t}</span>
            </button>
          ))}
        </div>
      </div>
      <motion.div key={tab} role="tabpanel" id={`${uid}-panel`} aria-labelledby={`${uid}-${tab}`} className="tabpanel"
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease }}>
        {tab === 'Response plan' && <PlanTab a={a} />}
        {tab === 'Similar cases' && <CasesTab a={a} />}
        {tab === 'Strategy ranking' && <RankingTab a={a} />}
        {tab === 'Recovery' && <RecoveryTab a={a} />}
        {tab === 'Impact drivers' && <DriversTab a={a} />}
        {tab === 'Quality check' && <JudgeTab a={a} />}
        {tab === 'Agent trace' && <TraceTab a={a} />}
      </motion.div>

      <Feedback a={a} />
    </div>
  )
}
