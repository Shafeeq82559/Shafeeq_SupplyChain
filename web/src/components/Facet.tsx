import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { ease } from './motionkit'

type Val = string | number

/** A filter facet: a pill that opens a small checklist. Shows how many values are chosen, and optionally how many cases each has. */
export function Facet({ label, options, value, onChange, counts, single = false }: {
  label: string; options: readonly Val[]; value: Val[]; onChange: (v: Val[]) => void
  counts?: Record<string, number>; single?: boolean
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc) }
  }, [open])

  const pick = (o: Val) => {
    if (single) { onChange(value.includes(o) ? [] : [o]); setOpen(false); return }
    onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o])
  }
  const summary = value.length === 0 ? '' : value.length === 1 ? String(value[0]) : `${value.length} chosen`

  return (
    <div className="facet" ref={box}>
      <button className={`facet-btn ${value.length ? 'on' : ''}`} aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(!open)}>
        <span>{label}</span>{summary && <b>{summary}</b>}
        <svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" /></svg>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="facet-pop" role="group" aria-label={label} initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18, ease }}>
            <ul>
              {options.map((o) => (
                <li key={o}>
                  <button className={value.includes(o) ? 'sel' : ''} onClick={() => pick(o)} role={single ? 'radio' : 'checkbox'} aria-checked={value.includes(o)}>
                    <span className="box">{value.includes(o) && <svg viewBox="0 0 12 12"><path d="M2.5 6.3l2.4 2.4 4.6-5" /></svg>}</span>
                    <span className="opt">{o}</span>
                    {counts?.[String(o)] != null && <em className="num">{counts[String(o)].toLocaleString()}</em>}
                  </button>
                </li>
              ))}
            </ul>
            {value.length > 0 && <button className="facet-clear" onClick={() => onChange([])}>Clear {label.toLowerCase()}</button>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

const SEV_COLORS = ['#2e7d5b', '#8aa93a', '#d9a400', '#d9711c', '#c2452d']

/** Severity as five buttons: click one for an exact level, click another to stretch the range. */
export function SeverityPicker({ min, max, onChange }: { min: number; max: number; onChange: (min: number, max: number) => void }) {
  const click = (n: number) => {
    if (min === max && min !== n) onChange(Math.min(min, n), Math.max(min, n))
    else if (min === n && max === n) onChange(1, 5)
    else onChange(n, n)
  }
  const full = min === 1 && max === 5
  return (
    <div className={`sevpick ${full ? '' : 'on'}`} role="group" aria-label="Severity">
      <span>Severity</span>
      <div>
        {[1, 2, 3, 4, 5].map((n) => {
          const inRange = n >= min && n <= max && !full
          return (
            <button key={n} className={inRange ? 'in' : ''} style={{ ['--c' as string]: SEV_COLORS[n - 1] }} onClick={() => click(n)} aria-pressed={inRange} aria-label={`Severity ${n}`}>{n}</button>
          )
        })}
      </div>
    </div>
  )
}
