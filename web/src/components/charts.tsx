import { motion } from 'motion/react'
import { useId, useState } from 'react'
import { C, signed } from './chartkit'
import { ease } from './motionkit'


// ---------------------------------------------------------------- horizontal bars
export function HBars({ rows, max, format = (v) => String(Math.round(v)), highlight }: {
  rows: { label: string; value: number; sub?: string; color?: string }[]; max?: number; format?: (v: number) => string; highlight?: string
}) {
  const top = max ?? Math.max(...rows.map((r) => r.value), 1e-9)
  return (
    <div className="hbars">
      {rows.map((r, i) => (
        <div key={r.label} className={`hbar ${highlight === r.label ? 'hi' : ''}`}>
          <span className="hb-label">{r.label}{r.sub && <small>{r.sub}</small>}</span>
          <span className="hb-track"><motion.i style={{ width: `${(100 * r.value) / top}%`, background: r.color }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: 0.1 + i * 0.06, ease }} /></span>
          <b className="hb-val num">{format(r.value)}</b>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- diverging bars (factor effects)
export function Diverging({ rows, unit }: { rows: { label: string; value: string | number; contribution: number }[]; unit: string }) {
  const sorted = [...rows].sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution))
  const max = Math.max(...sorted.map((r) => Math.abs(r.contribution)), 1e-9)
  return (
    <div className="drows">
      {sorted.map((r, k) => {
        const up = r.contribution > 0
        return (
          <div key={r.label} className="drow">
            <div className="dlabel"><b>{r.label}</b><span>{String(r.value)}</span></div>
            <div className="dbar" aria-hidden="true">
              <span className="axis" />
              <motion.i className={up ? 'pos' : 'neg'} style={{ width: `${(Math.abs(r.contribution) / max) * 50}%`, [up ? 'left' : 'right']: '50%', transformOrigin: up ? 'left' : 'right' }}
                initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: 0.15 + k * 0.07, ease }} />
            </div>
            <b className={`dnum num ${up ? 'up' : 'down'}`}>{signed(r.contribution, unit)}</b>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------- waterfall: baseline -> prediction
export function Waterfall({ baseline, prediction, rows, unit, totalUnit, baseLabel = 'Typical case', endLabel = 'This case' }: {
  baseline: number; prediction: number; unit: string; totalUnit?: string; baseLabel?: string; endLabel?: string
  rows: { label: string; value: string | number; contribution: number }[]
}) {
  const steps = [...rows].sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution))
  const bars = steps.reduce<(typeof steps[number] & { from: number; to: number })[]>((acc, s) => {
    const from = acc.length ? acc[acc.length - 1].to : baseline
    return [...acc, { ...s, from, to: from + s.contribution }]
  }, [])
  const all = [baseline, prediction, ...bars.flatMap((b) => [b.from, b.to])]
  const lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.08 || 1
  const dmin = Math.max(0, lo - pad), dmax = hi + pad
  const pos = (v: number) => `${(100 * (v - dmin)) / (dmax - dmin)}%`
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1))
  const row = (key: string, label: string, sub: string, a: number, b: number, color: string, i: number, val: string, strong = false) => (
    <div key={key} className={`wrow ${strong ? 'strong' : ''}`}>
      <div className="dlabel"><b>{label}</b><span>{sub}</span></div>
      <div className="wtrack" aria-hidden="true">
        <motion.i style={{ left: pos(Math.min(a, b)), width: `calc(${pos(Math.max(a, b))} - ${pos(Math.min(a, b))})`, background: color, transformOrigin: 'left' }}
          initial={{ scaleX: 0, opacity: 0 }} animate={{ scaleX: 1, opacity: 1 }} transition={{ duration: 0.55, delay: 0.1 + i * 0.09, ease }} />
      </div>
      <b className="num wval">{val}</b>
    </div>
  )
  return (
    <div className="waterfall">
      {row('base', baseLabel, 'average of past cases', dmin, baseline, '#9fb0bb', 0, `${fmt(baseline)} ${totalUnit ?? unit}`, true)}
      {bars.map((b, i) => row(b.label, b.label, String(b.value), b.from, b.to, b.contribution > 0 ? C.rust : C.sea2, i + 1, signed(b.contribution, unit)))}
      {row('end', endLabel, 'model estimate', dmin, prediction, C.ink, bars.length + 1, `${fmt(prediction)} ${totalUnit ?? unit}`, true)}
    </div>
  )
}

// ---------------------------------------------------------------- semicircle gauge
export function Gauge({ value, max = 100, zones, label, sub }: {
  value: number; max?: number; label: string; sub?: string; zones: { upTo: number; color: string; tint: string }[]
}) {
  const r = 92, L = Math.PI * r
  const frac = Math.min(Math.max(value / max, 0), 1)
  const zone = zones.find((z) => value <= z.upTo) ?? zones[zones.length - 1]
  const arc = `M ${120 - r} 120 A ${r} ${r} 0 0 1 ${120 + r} 120`
  const ang = Math.PI * (1 - frac)
  const mx = 120 + r * Math.cos(ang), my = 120 - r * Math.sin(ang)
  const segs = zones.map((z, i) => ({ z, start: i ? zones[i - 1].upTo : 0 }))
  return (
    <div className="gauge" role="img" aria-label={`${label}: ${Math.round(value)} out of ${max}`}>
      <svg viewBox="0 0 240 150">
        {segs.map(({ z, start }) => (
          <path key={z.upTo} d={arc} fill="none" stroke={z.tint} strokeWidth="16" strokeDasharray={`${((z.upTo - start) / max) * L} ${L}`} strokeDashoffset={-(start / max) * L} />
        ))}
        <motion.path d={arc} fill="none" stroke={zone.color} strokeWidth="16" strokeLinecap="round" strokeDasharray={L}
          initial={{ strokeDashoffset: L }} animate={{ strokeDashoffset: L * (1 - frac) }} transition={{ duration: 1.3, delay: 0.2, ease }} />
        <motion.circle r="9" fill="var(--surface)" stroke={zone.color} strokeWidth="4" initial={{ cx: 120 - r, cy: 120, opacity: 0 }} animate={{ cx: mx, cy: my, opacity: 1 }} transition={{ duration: 1.3, delay: 0.2, ease }} />
      </svg>
      <div className="gauge-read"><b className="num" style={{ color: zone.color }}>{Math.round(value)}</b><span>{label}</span>{sub && <small>{sub}</small>}</div>
    </div>
  )
}

// ---------------------------------------------------------------- radar
export function Radar({ axes, format = (v) => `${Math.round(100 * v)}%` }: { axes: { label: string; value: number; detail?: string }[]; format?: (v: number) => string }) {
  const n = axes.length, cx = 170, cy = 160, R = 108
  const pt = (i: number, f: number) => { const a = -Math.PI / 2 + (2 * Math.PI * i) / n; return [cx + R * f * Math.cos(a), cy + R * f * Math.sin(a)] as const }
  const poly = axes.map((a, i) => pt(i, Math.min(a.value, 1)).join(',')).join(' ')
  return (
    <svg className="radar" viewBox="0 0 340 330" role="img" aria-label="Exposure by disruption type">
      {[0.25, 0.5, 0.75, 1].map((f) => <polygon key={f} points={axes.map((_, i) => pt(i, f).join(',')).join(' ')} fill="none" stroke={C.grid} strokeWidth="1" />)}
      {axes.map((_, i) => <line key={i} x1={cx} y1={cy} x2={pt(i, 1)[0]} y2={pt(i, 1)[1]} stroke={C.grid} />)}
      <motion.polygon points={poly} fill="rgba(194,69,45,.16)" stroke={C.rust} strokeWidth="2.2" strokeLinejoin="round"
        style={{ transformOrigin: `${cx}px ${cy}px`, transformBox: 'view-box' }} initial={{ scale: 0.15, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.9, delay: 0.15, ease }} />
      {axes.map((a, i) => {
        const [x, y] = pt(i, Math.min(a.value, 1)); const [lx, ly] = pt(i, 1.2)
        return (
          <g key={a.label}>
            <motion.circle cx={x} cy={y} r="4.5" fill="var(--surface)" stroke={C.rust} strokeWidth="2.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 + i * 0.05 }}><title>{`${a.label}: ${format(a.value)}${a.detail ? ' · ' + a.detail : ''}`}</title></motion.circle>
            <text x={lx} y={ly} textAnchor={lx < cx - 8 ? 'end' : lx > cx + 8 ? 'start' : 'middle'} dominantBaseline="middle" fontSize="12" fill={C.muted}>{a.label}</text>
          </g>
        )
      })}
    </svg>
  )
}

// ---------------------------------------------------------------- line chart with area
export function LineChart({ points, color = C.sea, format = (v) => String(Math.round(v)), xLabel, yLabel }: {
  points: { x: string; y: number }[]; color?: string; format?: (v: number) => string; xLabel?: string; yLabel?: string
}) {
  const id = useId().replace(/:/g, '')
  const W = 520, H = 250, l = 54, r = 36, t = 26, b = 48
  const maxY = Math.max(...points.map((p) => p.y)) * 1.15 || 1
  const sx = (i: number) => l + (i * (W - l - r)) / Math.max(points.length - 1, 1)
  const sy = (v: number) => t + (1 - v / maxY) * (H - t - b)
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${sx(i)} ${sy(p.y)}`).join(' ')
  const area = `${d} L${sx(points.length - 1)} ${H - b} L${sx(0)} ${H - b} Z`
  const [hover, setHover] = useState<number | null>(null)
  return (
    <svg className="linechart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={yLabel}>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".28" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}><line x1={l} x2={W - r} y1={sy(maxY * f)} y2={sy(maxY * f)} stroke={C.grid} strokeDasharray={f ? '3 5' : ''} />
          <text x={l - 8} y={sy(maxY * f)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill={C.muted}>{format(maxY * f)}</text></g>
      ))}
      <motion.path d={area} fill={`url(#${id})`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8, delay: 0.5 }} />
      <motion.path d={d} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease }} />
      {points.map((p, i) => (
        <g key={p.x} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          <motion.circle cx={sx(i)} cy={sy(p.y)} r={hover === i ? 7 : 5} fill="var(--surface)" stroke={color} strokeWidth="3" initial={{ opacity: 0, scale: 0 }} animate={{ opacity: 1, scale: 1 }}
            style={{ transformOrigin: `${sx(i)}px ${sy(p.y)}px`, transformBox: 'view-box' }} transition={{ delay: 0.5 + i * 0.12, type: 'spring', stiffness: 400, damping: 20 }} />
          <text x={sx(i)} y={sy(p.y) - 13} textAnchor="middle" fontSize="12" fontWeight="600" fill={C.ink} opacity={hover === null || hover === i ? 1 : 0.35}>{format(p.y)}</text>
          <text x={sx(i)} y={H - b + 20} textAnchor="middle" fontSize="12" fill={C.muted}>{p.x}</text>
          <rect x={sx(i) - 28} y={t} width="56" height={H - t - b} fill="transparent" />
        </g>
      ))}
      {xLabel && <text x={(l + W - r) / 2} y={H - 4} textAnchor="middle" fontSize="11.5" fill={C.muted}>{xLabel}</text>}
    </svg>
  )
}

// ---------------------------------------------------------------- heatmap
const mix = (a: number[], b: number[], f: number) => a.map((v, i) => Math.round(v + (b[i] - v) * f))
export function Heatmap({ rows, cols, data, unit = '' }: { rows: string[]; cols: string[]; data: Record<string, Record<string, number>>; unit?: string }) {
  const vals = rows.flatMap((r) => cols.map((c) => data[r]?.[c])).filter((v): v is number => typeof v === 'number')
  const lo = Math.min(...vals), hi = Math.max(...vals)
  const LOW = [60, 140, 136], MID = [244, 236, 210], HIGH = [192, 86, 63]
  const color = (v: number) => {
    const f = (v - lo) / (hi - lo || 1)
    const rgb = f < 0.5 ? mix(LOW, MID, f / 0.5) : mix(MID, HIGH, (f - 0.5) / 0.5)
    return { bg: `rgb(${rgb.join(',')})`, dark: f < 0.22 || f > 0.72 }
  }
  return (
    <div className="heat" style={{ gridTemplateColumns: `minmax(110px, 1.3fr) repeat(${cols.length}, minmax(64px, 1fr))` }}>
      <span />
      {cols.map((c) => <span key={c} className="heat-col">{c}</span>)}
      {rows.map((r, ri) => (
        <div key={r} className="heat-row">
          <span className="heat-rowlabel">{r}</span>
          {cols.map((c, ci) => {
            const v = data[r]?.[c]
            if (typeof v !== 'number') return <span key={c} className="heat-cell blank">–</span>
            const { bg, dark } = color(v)
            return (
              <motion.span key={c} className="heat-cell" style={{ background: bg, color: dark ? '#fff' : '#0f1f2e' }} title={`${r} · ${c}: ${Math.round(v)}${unit}`}
                initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.35, delay: 0.05 * (ri + ci) }}>{Math.round(v)}</motion.span>
            )
          })}
        </div>
      ))}
      <div className="heat-legend"><span>{Math.round(lo)}{unit} faster</span><i /><span>slower {Math.round(hi)}{unit}</span></div>
    </div>
  )
}

// ---------------------------------------------------------------- grouped columns
export function GroupedColumns({ groups, series, format = (v) => v.toFixed(2) }: {
  groups: string[]; series: { name: string; values: Record<string, number>; color: string }[]; format?: (v: number) => string
}) {
  return (
    <div className="gcols">
      <div className="gcols-legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
      <div className="gcols-body">
        {groups.map((g) => (
          <div key={g} className="gcol">
            <div className="gcol-bars">
              {series.map((s, si) => (
                <div key={s.name} className="gbar" title={`${s.name} · ${g}: ${format(s.values[g] ?? 0)}`}>
                  <motion.i style={{ height: `${Math.max((s.values[g] ?? 0) * 100, 1)}%`, background: s.color, transformOrigin: 'bottom' }}
                    initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ duration: 0.8, delay: 0.1 + si * 0.08, ease }} />
                  <em className="num">{format(s.values[g] ?? 0)}</em>
                </div>
              ))}
            </div>
            <span className="gcol-label">{g}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- stacked bar
export function StackBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  return (
    <div>
      <div className="stack" role="img" aria-label="Breakdown">
        {parts.map((p, i) => (
          <motion.span key={p.label} style={{ width: `${(100 * p.value) / total}%`, background: p.color, transformOrigin: 'left' }} title={`${p.label}: ${p.value.toFixed(1)}`}
            initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: 0.15 + i * 0.08, ease }} />
        ))}
      </div>
      <ul className="stack-legend">
        {parts.map((p) => <li key={p.label}><i style={{ background: p.color }} /><span>{p.label}</span><b className="num">{p.value % 1 ? p.value.toFixed(1) : p.value}</b></li>)}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------- bubble scatter (prioritization map)
export function Bubble({ items }: { items: { id: string; x: number; y: number; r: number; color: string; label: string; tip: string }[] }) {
  const W = 560, H = 330, l = 48, r = 24, t = 20, b = 44
  const sx = (v: number) => l + ((v - 0.5) / 5) * (W - l - r)
  const sy = (v: number) => t + (1 - v / 100) * (H - t - b)
  return (
    <svg className="bubble" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Severity against production impact; bubble size is revenue loss">
      {[0, 25, 50, 75, 100].map((v) => <g key={v}><line x1={l} x2={W - r} y1={sy(v)} y2={sy(v)} stroke={C.grid} strokeDasharray={v ? '3 5' : ''} /><text x={l - 8} y={sy(v)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill={C.muted}>{v}%</text></g>)}
      {[1, 2, 3, 4, 5].map((v) => <text key={v} x={sx(v)} y={H - b + 20} textAnchor="middle" fontSize="12" fill={C.muted}>{v}</text>)}
      <text x={(l + W - r) / 2} y={H - 6} textAnchor="middle" fontSize="11.5" fill={C.muted}>Severity</text>
      <text x={12} y={(t + H - b) / 2} textAnchor="middle" fontSize="11.5" fill={C.muted} transform={`rotate(-90 12 ${(t + H - b) / 2})`}>Production impact</text>
      {items.map((it, i) => (
        <g key={it.id}>
          <motion.circle cx={sx(it.x)} cy={sy(it.y)} r={it.r} fill={it.color} fillOpacity=".78" stroke="var(--surface)" strokeWidth="2" style={{ transformOrigin: `${sx(it.x)}px ${sy(it.y)}px`, transformBox: 'view-box' }}
            initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 220, damping: 18, delay: 0.1 + i * 0.09 }}><title>{it.tip}</title></motion.circle>
          <text x={sx(it.x)} y={sy(it.y) - it.r - 6} textAnchor="middle" fontSize="11.5" fontWeight="600" fill={C.ink}>{it.label}</text>
        </g>
      ))}
    </svg>
  )
}
