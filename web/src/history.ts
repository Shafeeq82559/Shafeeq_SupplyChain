import { useSyncExternalStore } from 'react'
import type { Analysis, Overrides } from './api'

export interface HistoryEntry {
  id: string; ts: number; query: string; title: string; level: string; label: string; score: number; strategy: string
  a: Analysis; used: Overrides
}

const KEY = 'da.history.v1'
const MAX = 15
let cache: HistoryEntry[] | null = null
const listeners = new Set<() => void>()

function read(): HistoryEntry[] {
  if (cache) return cache
  try { cache = JSON.parse(localStorage.getItem(KEY) || '[]') as HistoryEntry[] } catch { cache = [] }
  return cache
}

function write(list: HistoryEntry[]) {
  let keep = list.slice(0, MAX)
  // browsers cap localStorage (about 5 MB): drop the oldest entries until the list fits
  for (;;) {
    try { localStorage.setItem(KEY, JSON.stringify(keep)); break } catch { if (keep.length <= 1) { keep = []; break } keep = keep.slice(0, -1) }
  }
  cache = keep
  listeners.forEach((f) => f())
}

export function addHistory(a: Analysis, used: Overrides) {
  const p = a.impact_assessment.priority
  const entry: HistoryEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, ts: Date.now(), query: a.query,
    title: `${a.profile.disruption_type} in ${a.profile.industry.toLowerCase()}, ${a.profile.supplier_region}`,
    level: p.priority_level, label: p.priority_label, score: p.priority_score, strategy: a.response.plan.recommended_strategy, a, used,
  }
  write([entry, ...read().filter((e) => e.query !== entry.query)])
}
export const removeHistory = (id: string) => write(read().filter((e) => e.id !== id))
export const clearHistory = () => write([])

const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } }
export const useHistory = () => useSyncExternalStore(subscribe, read)

export function timeAgo(ts: number): string {
  const s = Math.max(1, Math.round((Date.now() - ts) / 1000))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
