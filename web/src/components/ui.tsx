import { motion } from 'motion/react'
import { useId, type ReactNode } from 'react'
import { rise } from './motionkit'

export function PageHead({ title, lede }: { title: string; lede: string }) {
  return (
    <motion.div className="pagehead" {...rise(0)}>
      <h2>{title}</h2>
      <p>{lede}</p>
    </motion.div>
  )
}

export function SelectField({ label, value, options, onChange, empty }: {
  label: string; value: string; options: readonly (string | number)[]; onChange: (v: string) => void; empty?: string
}) {
  return (
    <label className="field">{label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {empty !== undefined && <option value="">{empty}</option>}
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  )
}

export function Slider({ label, value, min, max, step = 1, onChange, format, disabled }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; format?: (v: number) => string; disabled?: boolean
}) {
  const id = useId()
  const fill = ((value - min) / (max - min)) * 100
  return (
    <div className={`field slider ${disabled ? 'off' : ''}`}>
      <label htmlFor={id}>{label}<b className="num">{format ? format(value) : value}</b></label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        style={{ ['--fill' as string]: `${fill}%` }} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  )
}

export function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} className="switch" onClick={() => onChange(!checked)}>
      <span className="switch-track"><motion.i layout transition={{ type: 'spring', stiffness: 600, damping: 36 }} style={{ marginLeft: checked ? 18 : 0 }} /></span>
      <span>{label}{hint && <small>{hint}</small>}</span>
    </button>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: readonly { id: T; label: string }[]; onChange: (v: T) => void; label: string
}) {
  const uid = useId()
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} aria-pressed={o.id === value} onClick={() => onChange(o.id)}>
          {o.id === value && <motion.span layoutId={`seg-${uid}`} className="seg-bg" transition={{ type: 'spring', stiffness: 520, damping: 40 }} />}
          <span className="lbl">{o.label}</span>
        </button>
      ))}
    </div>
  )
}

/** Multi-select as toggleable chips (used for search filters). */
export function ChipGroup({ label, options, value, onChange }: {
  label: string; options: readonly (string | number)[]; value: (string | number)[]; onChange: (v: (string | number)[]) => void
}) {
  const toggle = (o: string | number) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o])
  return (
    <div className="field">
      {label}
      <div className="chips tight" role="group" aria-label={label}>
        {options.map((o) => <button key={o} className="chip" aria-pressed={value.includes(o)} onClick={() => toggle(o)}>{o}</button>)}
      </div>
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <motion.div className="emptystate" {...rise(0)}>
      <svg viewBox="0 0 120 40" aria-hidden="true"><path d="M4 30 C30 6, 60 38, 116 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2 6" strokeLinecap="round" />
        <circle cx="4" cy="30" r="3.5" fill="currentColor" /><rect x="106" y="4" width="14" height="9" rx="1.5" fill="#f2a900" /></svg>
      <b>{title}</b>
      {children && <p>{children}</p>}
    </motion.div>
  )
}

export function Skeleton({ h = 120, className = '' }: { h?: number; className?: string }) {
  return <div className={`skeleton ${className}`} style={{ height: h }} aria-hidden="true" />
}
