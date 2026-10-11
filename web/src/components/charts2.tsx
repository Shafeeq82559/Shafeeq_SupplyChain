import { motion } from 'motion/react'
import { C } from './chartkit'
import { ease } from './motionkit'

// ---------------------------------------------------------------- donut
export function Donut({ parts, centre, sub }: { parts: { label: string; value: number; color: string }[]; centre: string; sub: string }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  const r = 52, L = 2 * Math.PI * r
  const segs = parts.reduce<{ p: (typeof parts)[number]; start: number; len: number }[]>((acc, p) => {
    const start = acc.length ? acc[acc.length - 1].start + acc[acc.length - 1].len : 0
    return [...acc, { p, start, len: (p.value / total) * L }]
  }, [])
  return (
    <div className="donut">
      <svg viewBox="0 0 140 140" role="img" aria-label="Share of each response">
        <circle cx="70" cy="70" r={r} fill="none" stroke={C.grid} strokeWidth="16" opacity=".4" />
        {segs.map(({ p, start, len }, i) => (
          <motion.circle key={p.label} cx="70" cy="70" r={r} fill="none" stroke={p.color} strokeWidth="16" transform="rotate(-90 70 70)"
            strokeDasharray={`${Math.max(len - 2, 0.5)} ${L}`} strokeDashoffset={-start}
            initial={{ opacity: 0, strokeWidth: 6 }} animate={{ opacity: 1, strokeWidth: 16 }} transition={{ duration: 0.6, delay: 0.15 + i * 0.1, ease }}>
            <title>{`${p.label}: ${p.value} of ${total}`}</title>
          </motion.circle>
        ))}
        <text x="70" y="68" textAnchor="middle" fontSize="24" fontWeight="700" fill={C.ink} fontFamily="var(--display)">{centre}</text>
        <text x="70" y="86" textAnchor="middle" fontSize="10.5" fill={C.muted}>{sub}</text>
      </svg>
      <ul className="donut-legend">
        {parts.map((p) => <li key={p.label}><i style={{ background: p.color }} /><span>{p.label}</span><b className="num">{p.value}</b></li>)}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------- scatter
export interface Dot { id: string; x: number; y: number; color: string; label: string; tip: string }
export function Scatter({ dots, xLabel, yLabel, xFormat = (v) => String(Math.round(v)), yFormat = (v) => `${Math.round(v)}%` }: {
  dots: Dot[]; xLabel: string; yLabel: string; xFormat?: (v: number) => string; yFormat?: (v: number) => string
}) {
  const W = 520, H = 290, l = 50, r = 22, t = 20, b = 46
  const maxX = Math.max(...dots.map((d) => d.x), 1) * 1.1, maxY = Math.max(...dots.map((d) => d.y), 1) * 1.15
  const sx = (v: number) => l + (v / maxX) * (W - l - r)
  const sy = (v: number) => t + (1 - v / maxY) * (H - t - b)
  return (
    <svg className="scatter" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${yLabel} against ${xLabel}`}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line x1={l} x2={W - r} y1={sy(maxY * f)} y2={sy(maxY * f)} stroke={C.grid} strokeDasharray={f ? '3 5' : ''} />
          <text x={l - 8} y={sy(maxY * f)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill={C.muted}>{yFormat(maxY * f)}</text>
          <text x={sx(maxX * f)} y={H - b + 18} textAnchor="middle" fontSize="11" fill={C.muted}>{xFormat(maxX * f)}</text>
        </g>
      ))}
      <text x={(l + W - r) / 2} y={H - 6} textAnchor="middle" fontSize="11.5" fill={C.muted}>{xLabel}</text>
      <text x={12} y={(t + H - b) / 2} textAnchor="middle" fontSize="11.5" fill={C.muted} transform={`rotate(-90 12 ${(t + H - b) / 2})`}>{yLabel}</text>
      {dots.map((d, i) => (
        <motion.g key={d.id} className="sc-dot" style={{ transformOrigin: `${sx(d.x)}px ${sy(d.y)}px`, transformBox: 'view-box' }}
          initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 260, damping: 16, delay: 0.1 + i * 0.05 }}>
          <circle cx={sx(d.x)} cy={sy(d.y)} r="12" fill={d.color} fillOpacity=".88" stroke="var(--surface)" strokeWidth="2"><title>{d.tip}</title></circle>
          <text x={sx(d.x)} y={sy(d.y)} textAnchor="middle" dominantBaseline="central" fontSize="10.5" fontWeight="700" fill="var(--surface)" pointerEvents="none">{d.label}</text>
        </motion.g>
      ))}
    </svg>
  )
}
