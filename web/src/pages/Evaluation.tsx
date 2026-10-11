import { motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { api, type Evaluation as EvalData } from '../api'
import { HBars } from '../components/charts'
import { ease, rise } from '../components/motionkit'
import { PageHead, Skeleton } from '../components/ui'
import { pct, useCountUp } from '../lib'

const f2 = (v: number) => v.toFixed(2)

/** Circular score for a 0..1 value, counting up. */
function Ring({ value, display, label, sub, delay = 0 }: { value: number; display: (v: number) => string; label: string; sub: string; delay?: number }) {
  const r = 46, L = 2 * Math.PI * r
  const shown = useCountUp(value, 1100, 300 + delay * 100)
  return (
    <motion.div className="hring" {...rise(delay)}>
      <svg viewBox="0 0 110 110" role="img" aria-label={`${label}: ${display(value)}`}>
        <circle cx="55" cy="55" r={r} className="hr-track" />
        <motion.circle cx="55" cy="55" r={r} className="hr-bar" strokeDasharray={L} initial={{ strokeDashoffset: L }} animate={{ strokeDashoffset: L * (1 - Math.min(value, 1)) }} transition={{ duration: 1.3, delay: 0.3 + delay * 0.1, ease }} />
      </svg>
      <b className="num">{display(shown)}</b>
      <span className="hr-label">{label}</span>
      <small>{sub}</small>
    </motion.div>
  )
}

function Tier({ kind, children }: { kind: 'strong' | 'solid' | 'limit' | 'work'; children: ReactNode }) {
  return <span className={`etier ${kind}`}>{children}</span>
}

function Strong({ i, title, big, unit, meaning, children }: { i: number; title: string; big: string; unit?: string; meaning: string; children?: ReactNode }) {
  return (
    <motion.article className="ecard" initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ duration: 0.5, delay: (i % 3) * 0.08, ease }}>
      <div className="ecard-top"><h4>{title}</h4><Tier kind="strong">Strong</Tier></div>
      <b className="ebig num">{big}{unit && <small>{unit}</small>}</b>
      <p className="emean">{meaning}</p>
      {children && <div className="evis">{children}</div>}
    </motion.article>
  )
}

function WeakRow({ title, tag, kind, big, why }: { title: string; tag: string; kind: 'limit' | 'work'; big: string; why: string }) {
  return (
    <div className={`wrow ${kind}`}>
      <div className="wr-name"><b>{title}</b><Tier kind={kind}>{tag}</Tier></div>
      <b className="wr-num num">{big}</b>
      <p>{why}</p>
    </div>
  )
}

const FRAMEWORK_METRICS: Record<string, [string, string]> = {
  answer_relevancy: ['Answer relevancy', 'Does the plan answer the question that was asked?'],
  faithfulness: ['Faithfulness', 'Does every claim stick to the evidence it was given?'],
  faithfulness_explanation: ['Faithfulness (explanation only)', 'The same check on the written rationale alone, without action steps.'],
  contextual_precision: ['Context precision', 'Were the most useful cases ranked first?'],
  context_precision: ['Context precision', 'Were the most useful cases ranked first?'],
  contextual_recall: ['Context recall', 'Did the evidence cover what the reference answer says?'],
  context_recall: ['Context recall', 'Did the evidence cover what the reference answer says?'],
  recommendation_quality: ['Recommendation quality', 'Does the chosen strategy match the reference strategy?'],
  analysis_correctness: ['Analysis correctness', 'Are the numbers and reasoning in the analysis right?'],
}

/** One framework, shown on its own: its judge, sample size and every metric it reported. */
function FrameworkPanel({ name, blurb, data, judge, delay }: { name: string; blurb: string; data: { n_cases?: number; summary: Record<string, { mean: number }> }; judge: string; delay: number }) {
  return (
    <motion.section className="fwpanel" {...rise(delay)}>
      <header><div><h4>{name}</h4><p>{blurb}</p></div><span className="fwmeta"><b className="num">{data.n_cases}</b> scenarios<small>judge: {judge}</small></span></header>
      <div className="fwrows">
        {Object.entries(data.summary).map(([k, v], i) => {
          const [label, hint] = FRAMEWORK_METRICS[k] ?? [k.replace(/_/g, ' '), '']
          const band = v.mean >= 0.8 ? 'hi' : v.mean >= 0.55 ? 'mid' : 'lo'
          return (
            <div key={k} className="fwrow">
              <div className="fwtop"><span>{label}</span><b className="num">{f2(v.mean)}</b></div>
              <span className="fwtrack"><motion.i className={band} style={{ width: `${Math.max(v.mean * 100, 1.5)}%` }} initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.8, delay: i * 0.06, ease }} /></span>
              {hint && <small>{hint}</small>}
            </div>
          )
        })}
      </div>
    </motion.section>
  )
}

export function Evaluation() {
  const [ev, setEv] = useState<EvalData | null | undefined>(undefined)
  useEffect(() => { api.evaluation().then(setEv).catch(() => setEv(null)) }, [])

  const head = <PageHead title="How well does it work?" lede="The results of every test we ran, the strong ones first. Where a number is weaker, we say why and what we do about it." />
  if (ev === undefined) return <div className="wrap page-body">{head}<div className="stackgap"><Skeleton h={220} /><Skeleton h={260} /><Skeleton h={260} /></div></div>
  const mm = ev?.model_metrics, se = ev?.search_eval, de = ev?.deepeval_results?.summary, rg = ev?.ragas_results?.summary, jd = ev?.llm_judge_eval, cl = ev?.classification_eval?.results
  if (!ev || !mm || !se || !de || !rg || !jd || !cl) {
    return <div className="wrap page-body">{head}<div className="notice error" role="alert"><div><b>The evaluation results could not be loaded.</b> Make sure the API is running and that <code>python -m scripts.run_evaluation</code> has produced results.</div></div></div>
  }

  const key = 'loose (type + industry)', strict = 'strict (type + industry + severity +/-1)'
  const hy = se.results['hybrid a=0.6 (default)'], kw = se.results.keyword, sm = se.results.semantic
  const llm = cl.llm_agent
  const regs = [['production_impact_pct', 'Production impact'], ['revenue_loss_usd', 'Revenue loss'], ['full_recovery_days', 'Full recovery time'], ['partial_recovery_days', 'Partial recovery time']] as const
  const judgeName = (jd.judge_model ?? 'the judge model').replace('claude-sonnet-5-5', 'Claude Sonnet 5.5')
  const llmAcc = llm ? Math.min(...Object.values(llm.accuracy)) : 0

  return (
    <div className="wrap page-body evalpage">
      {head}

      <motion.section className="evalhero" {...rise(1)}>
        <div className="evalhero-rings">
          <Ring value={mm.high_impact.ROC_AUC ?? 0} display={f2} label="Spots high-impact disruptions" sub="ROC-AUC, on data it never saw" delay={0} />
          <Ring value={hy[key]['precision@10'] ?? 0} display={(v) => (v * 10).toFixed(1) + ' / 10'} label="Finds the right past cases" sub={`${se.n_queries} test searches`} delay={1} />
          <Ring value={llmAcc} display={(v) => `${Math.round(v * 100)}%`} label="Understands your description" sub="type, industry, region, tier, backup" delay={2} />
          <Ring value={de.faithfulness.mean} display={f2} label="Answers stay true to the evidence" sub="DeepEval faithfulness" delay={3} />
        </div>
        <p className="evalhero-note">Strong where the data allows it, and honest where it does not. Every score below was produced by tests we ran on this system. The language-model grading was done with {judgeName}.</p>
      </motion.section>

      <h3 className="esec"><span>What it does well</span><Tier kind="strong">Strongest results</Tier></h3>
      <div className="egrid">
        <Strong i={0} title="Spots high-impact disruptions" big={f2(mm.high_impact.ROC_AUC ?? 0)} unit=" ROC-AUC"
          meaning="Given a disruption, it ranks the ones that will hurt most far above the rest. 0.5 would be a coin toss and 1.0 perfect.">
          <HBars max={1} rows={[{ label: 'Precision', value: mm.high_impact.precision ?? 0 }, { label: 'Recall', value: mm.high_impact.recall ?? 0 }, { label: 'F1 score', value: mm.high_impact.F1 ?? 0, color: '#2e7d5b' }]} format={f2} />
        </Strong>
        <Strong i={1} title="Predicts production impact" big={f2(mm.production_impact_pct.R2 ?? 0)} unit=" R²"
          meaning={`It is off by ${(mm.production_impact_pct.MAE ?? 0).toFixed(1)} percentage points on average. Guessing the average would be off by ${(mm.production_impact_pct.baseline_MAE ?? 0).toFixed(1)}.`}>
          <HBars rows={[{ label: 'Our model', value: mm.production_impact_pct.MAE ?? 0, color: '#14506b' }, { label: 'Guessing the average', value: mm.production_impact_pct.baseline_MAE ?? 0, color: '#9fb0bb' }]} format={(v) => `${v.toFixed(1)} pts`} />
        </Strong>
        <Strong i={2} title="Honest ranges" big="78 to 79" unit="% inside"
          meaning="Every estimate comes with a likely range. The real answer landed inside it about 4 times in 5, as intended (the target is 80%).">
          <HBars max={1} rows={regs.map(([k, name]) => ({ label: name, value: mm[k].interval_coverage_p10_p90 ?? 0, color: '#1d7a9e' }))} format={(v) => pct(v)} />
        </Strong>
        <Strong i={3} title="Finds the right past cases" big={(hy[key]['precision@10'] * 10).toFixed(1)} unit=" of 10"
          meaning={`Of the top 10 cases, this many have the right disruption type and industry. The very first result is right ${pct(hy[key]['hit@1'])} of the time.`}>
          <HBars max={10} rows={[{ label: 'Keywords only', value: kw[key]['precision@10'] * 10, color: '#9fb0bb' }, { label: 'Meaning only', value: sm[key]['precision@10'] * 10, color: '#1d7a9e' }, { label: 'Hybrid (default)', value: hy[key]['precision@10'] * 10, color: '#14506b' }]} format={(v) => v.toFixed(1)} />
        </Strong>
        <Strong i={4} title="Understands your description" big={`${Math.round(llmAcc * 100)}%`}
          meaning="Reading a plain-English description, it got the disruption type, industry, region, supplier tier and backup status right every time, and its severity guess was never more than 1 off.">
          <HBars max={1} rows={[{ label: 'Disruption type', value: llm.accuracy.disruption_type }, { label: 'Industry', value: llm.accuracy.industry }, { label: 'Region', value: llm.accuracy.supplier_region }, { label: 'Tier', value: llm.accuracy.supplier_tier }, { label: 'Backup supplier', value: llm.accuracy.has_backup_supplier }]} format={(v) => pct(v)} />
        </Strong>
        <Strong i={5} title="Relevant, grounded answers" big={f2(de.answer_relevancy.mean)} unit=" relevancy"
          meaning={`The written plans answer the question that was asked and stick to the evidence they were given. ${jd.pass_rate >= 1 ? 'Every plan also passed' : `${pct(jd.pass_rate)} of plans also passed`} the built-in quality check.`}>
          <HBars max={1} rows={[{ label: 'Answer relevancy', value: de.answer_relevancy.mean }, { label: 'Faithfulness', value: de.faithfulness.mean }, { label: 'Context precision', value: de.contextual_precision.mean }, { label: 'Analysis correctness', value: de.analysis_correctness.mean }]} format={f2} />
          <p className="judgeline"><b className="num">{jd.mean_overall.toFixed(2)} / 5</b> average judge score, <b className="num">{pct(jd.pass_rate)}</b> pass rate</p>
        </Strong>
      </div>

      <div className="duo">
        <motion.section className="card" {...rise(1)}>
          <h4>Search, with the harder test</h4>
          <p className="muted blurb">Counting a result as right only if the severity is within one level as well.</p>
          <HBars max={10} rows={[{ label: 'Keywords only', value: kw[strict]['precision@10'] * 10, color: '#9fb0bb' }, { label: 'Meaning only', value: sm[strict]['precision@10'] * 10, color: '#1d7a9e' }, { label: 'Hybrid (default)', value: hy[strict]['precision@10'] * 10, color: '#14506b' }]} format={(v) => `${v.toFixed(1)} of 10`} />
        </motion.section>
        <motion.section className="card" {...rise(2)}>
          <h4>What the judge scored, out of 5</h4>
          <p className="muted blurb">Five criteria on {jd.n_cases} full plans. Relevance is the strongest, actionability and completeness leave room to grow.</p>
          <HBars max={5} rows={Object.entries(jd.mean_by_criterion).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k[0].toUpperCase() + k.slice(1), value: v, color: v >= 4.5 ? '#2e7d5b' : '#14506b' }))} format={(v) => v.toFixed(1)} />
        </motion.section>
      </div>

      <h3 className="esec"><span>DeepEval and RAGAS, side by side</span><Tier kind="solid">Two separate tests</Tier></h3>
      <p className="muted blurb fwintro">Two independent toolkits grade the same {ev.deepeval_results?.n_cases} plans. They ask different questions, so their scores are shown apart and never averaged.</p>
      <div className="fwgrid">
        <FrameworkPanel name="DeepEval" blurb="Grades answer, evidence and strategy" data={ev.deepeval_results!} judge={judgeName} delay={0} />
        <FrameworkPanel name="RAGAS" blurb="Checks claims one by one against the evidence" data={ev.ragas_results!} judge={(ev.ragas_results?.judge_model ?? 'the judge model').replace('claude-sonnet-5-5', 'Claude Sonnet 5.5').replace(' (OpenAI-compatible)', '')} delay={1} />
      </div>

      <h3 className="esec"><span>Where it is weaker</span><Tier kind="limit">In short</Tier></h3>
      <motion.section className="card weaklist" {...rise(1)}>
        <WeakRow kind="limit" tag="Data limit" title="Revenue loss" big={`R² ${f2(mm.revenue_loss_usd.R2 ?? 0)}`} why="Depends on company size, which is not in the data. Shown as a range." />
        <WeakRow kind="limit" tag="Data limit" title="Recovery time" big={`R² ${f2(mm.full_recovery_days.R2 ?? 0)} / ${f2(mm.partial_recovery_days.R2 ?? 0)}`} why="Local details are not recorded, and three different algorithms score the same." />
        <WeakRow kind="limit" tag="Data limit" title="Supplier replaced?" big={`AUC ${f2(mm.permanent_supplier_change.ROC_AUC ?? 0)}`} why="Barely tied to the recorded facts, so a weak signal." />
        <WeakRow kind="work" tag="Strict test" title="RAGAS faithfulness" big={`${f2(rg.faithfulness.mean)} / ${f2(rg.faithfulness_explanation.mean)}`} why="Action steps count as unsupported claims. The explanation alone scores higher." />
      </motion.section>
    </div>
  )
}
