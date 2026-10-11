import { motion } from 'motion/react'
import { useState } from 'react'
import { api, ApiError, type Analysis } from '../api'
import { RESPONSES } from '../lib'

export function Feedback({ a }: { a: Analysis }) {
  const plan = a.response.plan
  const [rating, setRating] = useState(4)
  const [helpful, setHelpful] = useState(true)
  const [chosen, setChosen] = useState(RESPONSES.includes(plan.recommended_strategy) ? plan.recommended_strategy : RESPONSES[0])
  const [comment, setComment] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [error, setError] = useState<string | null>(null)

  const send = async () => {
    setState('sending'); setError(null)
    try {
      await api.feedback({
        query: a.query, endpoint: 'analyze', rating, helpful, comment: comment || null,
        recommended_strategy: plan.recommended_strategy, chosen_strategy: chosen, cited_cases: plan.cited_cases ?? [],
        plan_text: JSON.stringify(plan).slice(0, 4900),
      })
      setState('sent')
    } catch (e) {
      setState('idle'); setError(e instanceof ApiError ? e.message : 'Feedback was not saved. Try again.')
    }
  }

  return (
    <section className="panel feedback">
      <h3>Was this analysis useful?</h3>
      {state === 'sent' ? (
        <motion.p className="success" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
          Feedback saved. It will shape how strategies are ranked from now on.
        </motion.p>
      ) : (
        <>
          <div className="fb-grid">
            <div className="field">Rating
              <div className="stars" role="group" aria-label="Rating">
                {[1, 2, 3, 4, 5].map((n) => <button key={n} aria-pressed={rating === n} onClick={() => setRating(n)}>{n}</button>)}
              </div>
            </div>
            <div className="field">Helpful?
              <div className="tri" role="group" aria-label="Helpful">
                <button aria-pressed={helpful} onClick={() => setHelpful(true)}>Yes</button>
                <button aria-pressed={!helpful} onClick={() => setHelpful(false)}>No</button>
              </div>
            </div>
            <label className="field">Strategy you will actually use
              <select value={chosen} onChange={(e) => setChosen(e.target.value)}>{RESPONSES.map((r) => <option key={r}>{r}</option>)}</select>
            </label>
          </div>
          <label className="field" style={{ marginTop: 16 }}>Comment (optional)
            <input type="text" value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          {error && <div className="notice error"><div>{error}</div></div>}
          <div style={{ marginTop: 16 }}>
            <button className="btn" onClick={send} disabled={state === 'sending'}>{state === 'sending' ? 'Saving' : 'Save feedback'}</button>
          </div>
        </>
      )}
    </section>
  )
}
