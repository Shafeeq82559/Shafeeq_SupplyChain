import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { Range } from '../api'
import { useCountUp } from '../lib'
import { ease, rise } from './motionkit'

const ICONS: Record<string, ReactNode> = {
  gauge: <><path d="M4 16a8 8 0 1 1 16 0" /><path d="M12 16l4-5" /></>,
  coin: <><circle cx="12" cy="12" r="8" /><path d="M12 8v8M9.5 10.2c.6-.8 1.5-1.2 2.5-1.2 1.4 0 2.5.7 2.5 1.8 0 2.4-5 1.2-5 3.6 0 1.1 1.1 1.8 2.5 1.8 1 0 1.9-.4 2.5-1.2" /></>,
  clock: <><circle cx="12" cy="12" r="8" /><path d="M12 7.5V12l3 2" /></>,
  bolt: <path d="M13 3L5 13h6l-1 8 8-10h-6z" />,
  check: <><circle cx="12" cy="12" r="8" /><path d="M8.5 12.3l2.5 2.5 4.5-5" /></>,
  swap: <><path d="M5 8h13l-3-3M19 16H6l3 3" /></>,
  db: <><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></>,
  shield: <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />,
}
export function Icon({ name }: { name: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
}

export function Kpi({ i = 0, icon, label, range, value, format, max, note, tone = '', bar = true, meter }: {
  i?: number; icon: string; label: string; range?: Range; value?: number; format: (v: number) => string; max?: number
  note?: string; tone?: string; bar?: boolean; meter?: number
}) {
  const target = range ? range.predicted : value ?? 0
  const shown = useCountUp(target, 1000, 250 + i * 70)
  const top = max ?? (range ? range.high_p90 * 1.15 : 1)
  const at = (v: number) => `${100 * Math.min(v / top, 1)}%`
  return (
    <motion.div className={`kpi ${tone}`} {...rise(i + 1)}>
      <div className="kpi-top"><span className="kpi-icon"><Icon name={icon} /></span><span className="label">{label}</span></div>
      <div className="value" aria-label={`${label}: ${format(target)}`}>{format(shown)}</div>
      {range && bar && (
        <div className="range" aria-hidden="true">
          <motion.span className="band" style={{ left: at(range.low_p10), width: `calc(${at(range.high_p90)} - ${at(range.low_p10)})` }}
            initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.9, delay: 0.4 + i * 0.07, ease }} />
          <span className="mark" style={{ left: at(range.predicted) }} />
        </div>
      )}
      {meter !== undefined && (
        <div className="range" aria-hidden="true">
          <motion.span className="fill" initial={{ scaleX: 0 }} animate={{ scaleX: Math.min(meter, 1) }} transition={{ duration: 0.9, delay: 0.4 + i * 0.07, ease }} />
        </div>
      )}
      {note && <div className="note">{note}</div>}
    </motion.div>
  )
}
