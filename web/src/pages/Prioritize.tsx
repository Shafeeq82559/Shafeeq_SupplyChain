import { motion } from 'motion/react'
import { useRef, useState } from 'react'
import { api, ApiError, type PrioritizeResponse } from '../api'
import { Bubble, StackBar } from '../components/charts'
import { ease, rise } from '../components/motionkit'
import { PageHead, Skeleton } from '../components/ui'
import { money, PRIORITY_COLOR } from '../lib'

interface Row { key: number; id: string; sev: string; impact: string; loss: string; tier: string; backup: boolean }

const SAMPLE: Omit<Row, 'key'>[] = [
  { id: 'Typhoon, Taiwan chips', sev: '4', impact: '60', loss: '8000000', tier: '1', backup: false },
  { id: 'Port backlog, Rotterdam', sev: '2', impact: '18', loss: '400000', tier: '2', backup: true },
  { id: 'Ransomware attack', sev: '3', impact: '35', loss: '1500000', tier: '3', backup: false },
  { id: 'Strike, Mexico plant', sev: '3', impact: '42', loss: '2200000', tier: '1', backup: true },
  { id: 'Tariffs, packaging', sev: '1', impact: '6', loss: '90000', tier: '4', backup: true },
]
const FACTOR_COLORS: Record<string, string> = { severity: '#14506b', production_impact: '#1d7a9e', financial_loss: '#5fb0cf', supplier_tier: '#f2a900', no_backup: '#c2452d' }
const FACTOR_LABELS: Record<string, string> = { severity: 'Severity', production_impact: 'Production impact', financial_loss: 'Revenue loss', supplier_tier: 'Supplier tier', no_backup: 'No backup supplier' }
const SEVERITY = ['Minor', 'Moderate', 'Significant', 'Severe', 'Catastrophic']
const TIER = ['direct supplier', '2nd level', '3rd level', 'deepest']

// What each column means, in the words a planner would use. The percentages are the scoring weights in src/services/prioritization.py.
const GUIDE = [
  { t: 'Disruption', w: '', d: 'A label so you can recognise it, for example "Port strike, Rotterdam". The ranking never reads it, only the numbers in the other columns.' },
  { t: 'Severity', w: '35% of the score', d: 'How serious it is right now: 1 is a minor slowdown, 5 is a catastrophic shutdown.' },
  { t: 'Production impact', w: '25%', d: 'The share of your production this disruption stops or is expected to stop, from 0% to 100%.' },
  { t: 'Revenue loss', w: '25%', d: 'Money already lost or expected to be lost, in US dollars. Type the whole number, for example 250000.' },
  { t: 'Supplier tier', w: '10%', d: 'How far down your supply chain the hit supplier sits. 1 supplies you directly, 4 is the deepest. Closer means a faster hit.' },
  { t: 'Backup supplier', w: '5%', d: 'Say Yes if another supplier could cover the gap. Having none adds to the score.' },
]

export function Prioritize() {
  const next = useRef(SAMPLE.length)
  const [rows, setRows] = useState<Row[]>(SAMPLE.map((r, i) => ({ ...r, key: i })))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [res, setRes] = useState<PrioritizeResponse | null>(null)

  const upd = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const impactBad = (r: Row) => r.impact.trim() === '' || !(Number(r.impact) >= 0 && Number(r.impact) <= 100)
  const lossBad = (r: Row) => r.loss.trim() === '' || !(Number(r.loss) >= 0)
  const problems = rows.filter((r) => impactBad(r) || lossBad(r)).length

  const rank = async () => {
    setLoading(true); setError(null)
    try {
      const items = rows.map((r, i) => ({
        id: r.id.trim() || `Disruption ${i + 1}`, disruption_severity: Number(r.sev), production_impact_pct: Number(r.impact),
        revenue_loss_usd: Number(r.loss), supplier_tier: Number(r.tier), has_backup_supplier: r.backup,
      }))
      setRes(await api.prioritize(items))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Ranking failed. Try again.')
    } finally { setLoading(false) }
  }

  const top = res ? Math.max(...res.ranked.map((r) => r.priority_score), 1) : 1
  const maxLoss = res ? Math.max(...res.ranked.map((r) => r.revenue_loss_usd), 1) : 1

  return (
    <div className="wrap page-body">
      <PageHead title="Rank open disruptions" lede="Which problem should you deal with first? Add one row for each disruption you are facing. You get a score from 0 to 100 and a priority from P1 (critical) to P4 (low) for each, in order." />

      <motion.details className="fold guide" open {...rise(1)}>
        <summary>What goes in each column</summary>
        <div className="guide-grid">
          {GUIDE.map((g) => (
            <div key={g.t} className="guide-item"><b>{g.t}</b>{g.w && <em>{g.w}</em>}<p>{g.d}</p></div>
          ))}
        </div>
      </motion.details>

      <motion.section className="panel gridcard" {...rise(2)}>
        <div className="tablewrap flat">
          <table className="editable">
            <thead><tr>
              <th>Disruption<small>a name for it</small></th>
              <th>Severity<small>1 minor to 5 catastrophic</small></th>
              <th>Production impact<small>% of output lost</small></th>
              <th>Revenue loss<small>US dollars</small></th>
              <th>Supplier tier<small>1 direct to 4 deepest</small></th>
              <th>Backup supplier<small>can another cover?</small></th>
              <th />
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <motion.tr key={r.key} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <td><input className="cell wide" value={r.id} placeholder="Name this disruption" onChange={(e) => upd(r.key, { id: e.target.value })} aria-label="Disruption name" /></td>
                  <td><select className="cell" value={r.sev} onChange={(e) => upd(r.key, { sev: e.target.value })} aria-label="Severity">
                    {SEVERITY.map((s, i) => <option key={s} value={i + 1}>{i + 1} · {s}</option>)}</select></td>
                  <td><span className={`unit ${impactBad(r) ? 'invalid' : ''}`}>
                    <input className="cell" type="number" min={0} max={100} value={r.impact} onChange={(e) => upd(r.key, { impact: e.target.value })} aria-label="Production impact in percent" aria-invalid={impactBad(r)} /><i>%</i></span>
                    {impactBad(r) && <small className="cellhint bad">Enter 0 to 100</small>}</td>
                  <td><span className={`unit pre ${lossBad(r) ? 'invalid' : ''}`}><i>$</i>
                    <input className="cell" type="number" min={0} step={10000} value={r.loss} onChange={(e) => upd(r.key, { loss: e.target.value })} aria-label="Revenue loss in US dollars" aria-invalid={lossBad(r)} /></span>
                    {lossBad(r) ? <small className="cellhint bad">Enter an amount</small> : Number(r.loss) >= 1000 && <small className="cellhint">{money(Number(r.loss))}</small>}</td>
                  <td><select className="cell" value={r.tier} onChange={(e) => upd(r.key, { tier: e.target.value })} aria-label="Supplier tier">
                    {TIER.map((t, i) => <option key={t} value={i + 1}>Tier {i + 1} · {t}</option>)}</select></td>
                  <td><label className="yesno"><input type="checkbox" className="check" checked={r.backup} onChange={(e) => upd(r.key, { backup: e.target.checked })} />{r.backup ? 'Yes' : 'No'}</label></td>
                  <td><button className="iconbtn sm" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} disabled={rows.length <= 1} aria-label={`Remove ${r.id || 'row'}`}><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg></button></td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="gridfoot">
          <button className="btn ghost" onClick={() => setRows((rs) => [...rs, { key: next.current++, id: '', sev: '3', impact: '30', loss: '500000', tier: '2', backup: true }])}>Add a disruption</button>
          <button className="btn ghost" onClick={() => setRows(SAMPLE.map((r, i) => ({ ...r, key: next.current + i })))}>Use the example set</button>
          <span className="spacer" />
          {problems > 0 && <span className="muted gridwarn">Fix the {problems === 1 ? 'row' : `${problems} rows`} marked in red first.</span>}
          <button className="btn" onClick={rank} disabled={loading || problems > 0}>{loading ? 'Ranking' : 'Rank disruptions'}</button>
        </div>
      </motion.section>

      {loading && <div className="stackgap"><Skeleton h={80} /><Skeleton h={80} /><Skeleton h={80} /></div>}
      {error && !loading && <div className="notice error" role="alert"><div><b>Ranking failed.</b> {error}</div></div>}

      {res && !loading && (
        <>
          <h3 className="subhead big">Handle them in this order</h3>
          <p className="muted" style={{ marginTop: -6, marginBottom: 14 }}>Ranked only by the five numbers you entered. The names are just labels.</p>
          <div className="ranking prio">
            {res.ranked.map((r, i) => {
              const color = PRIORITY_COLOR[r.priority_level] ?? 'var(--muted)'
              const drivers = Object.entries(r.factor_contributions).filter(([, v]) => v >= 1).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k]) => FACTOR_LABELS[k] ?? k)
              return (
                <motion.div key={r.id + r.rank} className="prio-row" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.45, delay: i * 0.07, ease }}>
                  <span className="n num">{r.rank}</span>
                  <span className="placard" style={{ ['--c' as string]: color }}><b>{r.priority_level}</b><span>{r.priority_label}</span><em>{Math.round(r.priority_score)}</em></span>
                  <div className="what">
                    <b>{r.id}</b>
                    <span className="given">Severity {r.disruption_severity} of 5 · {r.production_impact_pct}% of production · {money(r.revenue_loss_usd)} lost · tier {r.supplier_tier} · {r.has_backup_supplier ? 'has a backup' : 'no backup'}</span>
                    <span>{r.recommended_action}</span>
                    {drivers.length > 0 && <small className="because">Ranked here mostly because of {drivers.join(' and ').toLowerCase()}.</small>}
                  </div>
                  <div className="prio-bars">
                    <div className="meter"><motion.i style={{ width: `${(100 * r.priority_score) / top}%`, background: color }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.9, delay: 0.15 + i * 0.07, ease }} /></div>
                    <div className="mini-stack">
                      {Object.entries(r.factor_contributions).map(([k, v]) => <span key={k} title={`${FACTOR_LABELS[k] ?? k}: ${v.toFixed(1)} points`} style={{ width: `${(100 * v) / Math.max(r.priority_score, 1)}%`, background: FACTOR_COLORS[k] ?? '#8ba3b3' }} />)}
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>

          <div className="duo">
            <motion.section className="card" {...rise(2)}>
              <h4>Where each disruption sits</h4>
              <p className="muted blurb">Higher and further right is worse. Bubble size is revenue loss.</p>
              <Bubble items={res.ranked.map((r) => ({
                id: r.id + r.rank, x: r.disruption_severity, y: r.production_impact_pct, r: 9 + 26 * Math.sqrt(r.revenue_loss_usd / maxLoss),
                color: PRIORITY_COLOR[r.priority_level] ?? '#8ba3b3',
                label: r.id.length > 18 ? r.id.slice(0, 17) + '…' : r.id, tip: `${r.id}: severity ${r.disruption_severity}, impact ${r.production_impact_pct}%, loss ${money(r.revenue_loss_usd)}`,
              }))} />
            </motion.section>
            <motion.section className="card" {...rise(3)}>
              <h4>How the score is worked out</h4>
              <p className="muted blurb">Every disruption is scored the same way, out of 100 points. The bar below is the first one in the list, point by point.</p>
              <StackBar parts={Object.entries(res.ranked[0].factor_contributions).map(([k, v]) => ({ label: FACTOR_LABELS[k] ?? k, value: v, color: FACTOR_COLORS[k] ?? '#8ba3b3' }))} />
              <h4 style={{ marginTop: 20 }}>How much each factor counts</h4>
              <ul className="weights">
                {Object.entries(res.weights).map(([k, w]) => <li key={k}><i style={{ background: FACTOR_COLORS[k] }} /><span>{FACTOR_LABELS[k] ?? k}</span><b className="num">{Math.round(100 * w)}%</b></li>)}
              </ul>
              <h4 style={{ marginTop: 20 }}>Priority levels</h4>
              <ul className="levels">
                {res.levels.map((l) => <li key={l.level}><span className="placard sm" style={{ ['--c' as string]: PRIORITY_COLOR[l.level] }}><b>{l.level}</b><span>{l.label}</span></span><em>from {l.min_score} points</em></li>)}
              </ul>
            </motion.section>
          </div>
        </>
      )}
    </div>
  )
}
