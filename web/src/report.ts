import type { Analysis, Overrides } from './api'
import { money, tidy } from './lib'

const esc = (s: unknown) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const list = (items: string[], ordered = false) => `<${ordered ? 'ol' : 'ul'}>${items.map((i) => `<li>${esc(i)}</li>`).join('')}</${ordered ? 'ol' : 'ul'}>`

const PRIORITY_HEX: Record<string, string> = { P1: '#c2452d', P2: '#d9711c', P3: '#b98900', P4: '#2e7d5b' }

/** A self-contained, print-ready HTML report of one analysis (opens in any browser; "Print to PDF" gives a PDF). */
export function buildReportHtml(a: Analysis, used: Overrides): string {
  const { predictions: p, priority: pr, drivers } = a.impact_assessment
  const plan = a.response.plan
  const rec = a.recovery
  const j = a.judgement
  const color = PRIORITY_HEX[pr.priority_level] ?? '#14506b'
  const title = `${a.profile.disruption_type} in ${a.profile.industry.toLowerCase()}, ${a.profile.supplier_region}`
  const when = new Date().toLocaleString(undefined, { dateStyle: 'long', timeStyle: 'short' })
  const row = (c: string[]) => `<tr>${c.map((x) => `<td>${x}</td>`).join('')}</tr>`
  const driverBlock = (name: string, d: { top: { label: string; value: string | number; contribution: number }[]; unit: string; summary: string }) =>
    `<h3>${name}</h3><table><tbody>${d.top.map((t) => row([esc(t.label), esc(t.value), `<b style="color:${t.contribution > 0 ? '#c2452d' : '#14506b'}">${t.contribution > 0 ? '+' : '−'}${Math.abs(t.contribution).toFixed(1)} ${esc(d.unit)}</b>`])).join('')}</tbody></table><p class="muted">${esc(d.summary)}</p>`

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Disruption briefing: ${esc(title)}</title>
<style>
  @page { margin: 16mm 14mm; }
  * { box-sizing: border-box; }
  body { font: 14px/1.55 'Segoe UI', system-ui, sans-serif; color: #0f1f2e; margin: 0; background: #fff; }
  .page { max-width: 820px; margin: 0 auto; padding: 36px 28px 60px; }
  header { border-bottom: 3px solid #0b1722; padding-bottom: 16px; margin-bottom: 22px; }
  header small { color: #5c6e7c; }
  h1 { font-size: 26px; margin: 8px 0 6px; line-height: 1.15; }
  h2 { font-size: 17px; margin: 28px 0 8px; padding-bottom: 5px; border-bottom: 1px solid #dce3e8; }
  h3 { font-size: 14px; margin: 16px 0 6px; }
  .badge { display: inline-block; padding: 3px 11px; border-radius: 999px; color: #fff; font-weight: 600; font-size: 12px; background: ${color}; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 14px 0; }
  .kpi { border: 1px solid #dce3e8; border-radius: 10px; padding: 10px 12px; break-inside: avoid; }
  .kpi span { display: block; color: #5c6e7c; font-size: 12px; } .kpi b { font-size: 20px; } .kpi em { display: block; font-style: normal; font-size: 11.5px; color: #5c6e7c; }
  .reco { background: #0b1722; color: #fff; border-radius: 12px; padding: 16px 20px; margin: 14px 0; break-inside: avoid; }
  .reco b { font-size: 20px; display: block; margin: 2px 0 4px; } .reco span { color: #b4c5d0; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin: 6px 0; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e7edf0; vertical-align: top; }
  th { color: #5c6e7c; font-weight: 600; background: #f6f9fb; }
  ul, ol { margin: 6px 0; padding-left: 20px; } li { margin: 3px 0; }
  .muted { color: #5c6e7c; font-size: 12.5px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  .note { background: #e4eff4; border-radius: 8px; padding: 8px 12px; font-size: 12.5px; margin: 8px 0; }
  footer { margin-top: 36px; color: #5c6e7c; font-size: 11.5px; border-top: 1px solid #dce3e8; padding-top: 10px; }
  @media print { .page { padding: 0; } body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head><body><div class="page">
<header><small>Supply Chain Disruption Assistant · Briefing · ${esc(when)}</small>
<h1>${esc(title)}</h1>
<span class="badge">${esc(pr.priority_level)} · ${esc(pr.priority_label)} · score ${Math.round(pr.priority_score)}</span>
<p><i>"${esc(a.query)}"</i></p></header>

<div class="reco"><span>Recommended response</span><b>${esc(plan.recommended_strategy)}</b>
<span>About ${Math.round(rec.timeline.full_recovery_days.predicted)} days to full recovery, ${Math.round(rec.timeline.partial_recovery_days.predicted)} days to partial recovery.${plan.fallback_strategy ? ` Fallback: ${esc(plan.fallback_strategy)}.` : ''}</span></div>

<div class="kpis">
  <div class="kpi"><span>Production impact</span><b>${p.production_impact_pct.predicted.toFixed(1)}%</b><em>likely ${p.production_impact_pct.low_p10.toFixed(0)}–${p.production_impact_pct.high_p90.toFixed(0)}%</em></div>
  <div class="kpi"><span>Revenue loss</span><b>${money(p.revenue_loss_usd.predicted)}</b><em>likely ${money(p.revenue_loss_usd.low_p10)}–${money(p.revenue_loss_usd.high_p90)}</em></div>
  <div class="kpi"><span>Full recovery</span><b>${Math.round(p.full_recovery_days.predicted)} days</b><em>likely ${Math.round(p.full_recovery_days.low_p10)}–${Math.round(p.full_recovery_days.high_p90)} days</em></div>
  <div class="kpi"><span>Chance of high impact</span><b>${Math.round(100 * p.high_impact_probability)}%</b><em>worst quarter of past cases</em></div>
  <div class="kpi"><span>Chance of switching supplier</span><b>${Math.round(100 * rec.supplier_change_probability)}%</b><em>${esc(rec.supplier_change_outlook)}</em></div>
  <div class="kpi"><span>Automated check</span><b>${j.overall_score.toFixed(1)}/5</b><em>${j.passed ? 'passed' : 'did not pass'} the quick check</em></div>
</div>

<h2>Summary</h2><p>${esc(a.executive_summary)}</p>
${Object.keys(used).length ? `<div class="note">Details supplied by the user: ${esc(Object.entries(used).map(([k, v]) => `${k.replace(/_/g, ' ')} = ${v}`).join(', '))}.</div>` : ''}
${a.assumptions?.length ? `<div class="note">Assumed: ${esc(a.assumptions.join('; '))}.</div>` : ''}

<h2>Why ${esc(plan.recommended_strategy)}</h2><p>${esc(plan.rationale)}</p>
<div class="cols"><div><h3>Do now</h3>${list(plan.immediate_actions, true)}</div><div><h3>Recovery plan</h3>${list(plan.recovery_plan)}</div></div>
<h3>Risks to watch</h3>${list(plan.risks)}

<h2>Strategy ranking</h2>
${a.response.basis ? `<p class="muted">Compared on ${esc(a.response.basis.description)}.</p>` : ''}
<table><thead><tr><th>#</th><th>Strategy</th><th>Score</th><th>Full recovery</th><th>Revenue loss</th><th>Supplier change</th><th>Past cases</th></tr></thead><tbody>
${a.response.strategy_ranking.map((r) => row([String(r.rank), `<b>${esc(r.response_type)}</b>`, String(Math.round(r.strategy_score)), `${Math.round(r.expected_full_recovery_days)} days`, money(r.expected_revenue_loss_usd), `${Math.round(100 * r.supplier_change_risk)}%`, `${r.evidence_cases} of ${r.evidence_total}`])).join('')}
</tbody></table>

<h2>Road to recovery</h2>
<table><tbody>${[...rec.milestones].sort((x, y) => x.day - y.day).map((m) => row([`<b>Day ${Math.round(m.day)}</b>`, esc(m.milestone)])).join('')}</tbody></table>
<p class="muted">Supplier resilience ${rec.resilience.resilience_score}/100 (${esc(rec.resilience.resilience_grade)}), risk band ${esc(rec.resilience.risk_band)}. Keep an eye on: ${esc(rec.monitoring_kpis.join(', '))}.</p>

<h2>What drives the estimates</h2>
${driverBlock('Recovery time', drivers.full_recovery_days)}${driverBlock('Production impact', drivers.production_impact_pct)}

<h2>Closest past cases</h2>
<p class="muted">${esc(a.investigation.historical_summary)}</p>
<table><thead><tr><th>Case</th><th>Response</th><th>Severity</th><th>Impact</th><th>Revenue loss</th><th>Recovery</th></tr></thead><tbody>
${a.investigation.similar_cases.map((c) => row([esc(c.disruption_id), esc(c.response_type), String(c.disruption_severity), `${c.production_impact_pct.toFixed(0)}%`, money(c.revenue_loss_usd), `${c.full_recovery_days} days`])).join('')}
</tbody></table>

<h2>Quality check</h2>
<table><tbody>${Object.entries(j.scores).map(([k, v]) => row([`<b>${esc(k.replace(/_/g, ' '))}</b>`, `${v}/5`, esc(j.reasons[k] ?? '')])).join('')}</tbody></table>

<h2>How it was produced</h2>
<table><tbody>${a.trace.map((s) => row([`<b>${esc(s.agent)}</b>`, `${s.duration_ms} ms`, esc(tidy(s.summary))])).join('')}</tbody></table>

<footer>Estimates come from models trained on 100,000 historical disruptions and are decision support, not a guarantee. Total analysis time ${(a.total_duration_ms / 1000).toFixed(1)}s.</footer>
</div></body></html>`
}

export function downloadFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** Opens the print dialog for the report (choose "Save as PDF" as the printer). Uses a hidden frame, so no pop-up is needed. */
export function printReport(html: string) {
  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  frame.srcdoc = html
  frame.onload = () => {
    frame.contentWindow?.focus()
    frame.contentWindow?.print()
    setTimeout(() => frame.remove(), 60000)
  }
  document.body.appendChild(frame)
}

export const reportName = (a: Analysis) =>
  `briefing-${a.profile.disruption_type}-${a.profile.industry}`.toLowerCase().replace(/[^a-z0-9]+/g, '-') + `-${new Date().toISOString().slice(0, 10)}`
