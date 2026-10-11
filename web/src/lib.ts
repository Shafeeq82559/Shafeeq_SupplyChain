import { useEffect, useRef, useState } from 'react'

export const TYPES = ['Port Congestion', 'Geopolitical', 'Labor Strike', 'Natural Disaster', 'Cyber Attack', 'Factory Incident']
export const INDUSTRIES = ['Electronics', 'Automotive', 'Consumer Goods', 'Pharmaceuticals', 'Aerospace']
export const REGIONS = ['Asia-Pacific', 'Europe', 'North America', 'South America', 'Africa/Middle East']
export const SIZES = ['Small', 'Medium', 'Large']
export const RESPONSES = ['Alternative Supplier', 'Production Reroute', 'Inventory Buffer', 'Customer Delay', 'Combined Strategy']

export const EXAMPLES: Record<string, string> = {
  'Typhoon hits Taiwan chip plant': "A typhoon flooded our Tier-1 semiconductor supplier's plant in Taiwan. Production is severely halted for weeks and we have no backup supplier.",
  'Ransomware at German auto supplier': 'Ransomware attack has locked the ERP systems of our Tier-2 auto parts supplier in Germany; shipments stopped for 5 days.',
  'Port strike delays pharma inputs': 'Dock workers union strike at the port is delaying containers of pharma active ingredients from India. Moderate delays so far, we have a backup supplier.',
  'Sanctions block titanium': 'New export sanctions blocked titanium deliveries from our aerospace components supplier in the Middle East.',
}

export const LLM_LABELS: Record<string, string> = {
  nvidia: 'NVIDIA', aicredits: 'GPT-5 nano', gemini: 'Gemini', anthropic: 'Claude', ollama: 'Ollama', off: 'Templates only',
}

export function money(v: number): string {
  return v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${Math.round(v / 1e3).toLocaleString()}K`
}

export const pct = (v: number, digits = 0) => `${(100 * v).toFixed(digits)}%`

export const PRIORITY_COLOR: Record<string, string> = {
  P1: '#c2452d', P2: '#c9661a', P3: '#a87d00', P4: '#2e7d5b',
}

/** Animates a number from 0 to `target`. Skips the animation when the user prefers reduced motion. */
export function useCountUp(target: number, ms = 900, delay = 0): number {
  const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [v, setV] = useState(0)
  const raf = useRef(0)
  useEffect(() => {
    if (reduced) return
    let start = 0
    const timer = window.setTimeout(() => {
      const tick = (t: number) => {
        start ||= t
        const p = Math.min((t - start) / ms, 1)
        setV(target * (1 - Math.pow(1 - p, 3)))
        if (p < 1) raf.current = requestAnimationFrame(tick)
      }
      raf.current = requestAnimationFrame(tick)
    }, delay)
    return () => { clearTimeout(timer); cancelAnimationFrame(raf.current) }
  }, [target, ms, delay, reduced])
  return reduced ? target : v
}

/** Turns leaked Python dict text such as {'industry': 'Automotive'} into plain words. */
export function tidy(text: string): string {
  return text.replace(/\{[^{}]*\}/g, (m) => {
    try {
      const obj = JSON.parse(m.replace(/'/g, '"').replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false')) as Record<string, unknown>
      return '(' + Object.entries(obj).map(([k, v]) => `${k.replace(/_/g, ' ')} ${String(v)}`).join(', ') + ')'
    } catch { return m }
  })
}

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))
const logit = (p: number) => { const q = Math.min(Math.max(p, 0.01), 0.99); return Math.log(q / (1 - q)) }

/** Yes/no models explain themselves in log-odds. Convert to percentage points: each factor is applied in turn on top of the average case. */
export function logOddsToPoints<T extends { contribution: number }>(baseline: number, prediction: number, rows: T[]) {
  const ordered = [...rows].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  let cum = baseline
  const converted = ordered.map((r) => { const from = sigmoid(cum); cum += r.contribution; return { ...r, contribution: 100 * (sigmoid(cum) - from) } })
  return { baseline: 100 * sigmoid(baseline), prediction: 100 * sigmoid(prediction), rows: converted }
}

/** Approximate effect of one log-odds driver on a probability, measured around the current probability. */
export function driverToPoints<T extends { contribution: number }>(probability: number, rows: T[]) {
  const L = logit(probability)
  return rows.map((r) => ({ ...r, contribution: 100 * (sigmoid(L + r.contribution / 2) - sigmoid(L - r.contribution / 2)) }))
}
