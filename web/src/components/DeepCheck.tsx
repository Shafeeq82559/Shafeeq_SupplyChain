import { useState } from 'react'
import { api, type DeepCheckResult, type Plan } from '../api'

const WHAT: Record<keyof DeepCheckResult['scores'], [string, string]> = {
  answer_relevancy: ['Answer relevancy', 'Does the plan answer the question that was asked?'],
  faithfulness: ['Faithfulness', 'Does every claim in the plan stick to the evidence it was given?'],
  analysis_correctness: ['Analysis correctness', 'Is the disruption characterised correctly, and are the claims about past cases supported?'],
  evidence_relevance: ['Evidence relevance', 'Was the evidence the AI was given relevant and sufficient for this answer?'],
}

const done = new Map<string, DeepCheckResult>() // keeps a finished check when switching tabs

const band = (v: number) => (v >= 0.8 ? 'hi' : v >= 0.55 ? 'mid' : 'lo')
const verdict = (v: number) => (v >= 0.8 ? 'Strong' : v >= 0.55 ? 'Fair' : 'Weak')

/** Optional DeepEval assessment of this one answer. Nothing runs until the user asks. */
export function DeepCheck({ query, plan }: { query: string; plan: Plan }) {
  const key = `${query}|${plan.recommended_strategy}|${plan.rationale}`
  const [result, setResult] = useState<DeepCheckResult | null>(done.get(key) ?? null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const run = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.deepCheck(query, plan)
      done.set(key, r); setResult(r)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="deepcheck">
      <header>
        <div>
          <h4>Deep check <span className="tag soft">DeepEval</span></h4>
          <p>An optional, slower check of this answer by DeepEval, an independent evaluation toolkit. It makes about ten language-model calls, so it takes anywhere from 20 seconds to a couple of minutes depending on the model.</p>
        </div>
        <button className="btn" onClick={run} disabled={busy || !plan.fact_sheet}>{busy ? 'Checking…' : result ? 'Run again' : 'Run deep check'}</button>
      </header>
      {!plan.fact_sheet && <p className="dc-note">This analysis has no saved evidence, so it cannot be checked.</p>}
      {busy && <p className="dc-note" role="status">Scoring this answer against its evidence. Please keep this page open.</p>}
      {err && <div className="notice error" role="alert"><div><b>The deep check could not finish.</b> {err}</div></div>}
      {result && (
        <div className="dc-results">
          {(Object.keys(WHAT) as (keyof DeepCheckResult['scores'])[]).map((k) => {
            const m = result.scores[k]
            const v = m?.score ?? null
            return (
              <div key={k} className="dc-row">
                <div className="dc-top"><span>{WHAT[k][0]}</span>{v == null ? <b className="muted">Not scored</b> : <b className="num">{v.toFixed(2)} <em className={band(v)}>{verdict(v)}</em></b>}</div>
                <span className="dc-track">{v != null && <i className={band(v)} style={{ width: `${Math.max(v * 100, 1.5)}%` }} />}</span>
                <small>{WHAT[k][1]}{result.errors[k] ? ` Not scored: ${result.errors[k]}.` : ''}</small>
                {m?.reason && <p className="dc-why"><b>Why:</b> {m.reason}</p>}
              </div>
            )
          })}
          <p className="dc-foot">Scored by {result.judge_model} against {result.n_contexts} pieces of evidence in {result.seconds}s. This is one answer, so treat it as an indication, not a verdict. DeepEval scores that need a reference answer, such as contextual precision and recall, are only available in the offline evaluation.</p>
        </div>
      )}
    </section>
  )
}
