import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'
const KEY = 'da.theme'

const system = (): Theme => (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
const stored = (): Theme | null => {
  try { const v = localStorage.getItem(KEY); return v === 'light' || v === 'dark' ? v : null } catch { return null }
}

export function applyTheme(t: Theme, animate = false) {
  const root = document.documentElement
  if (animate) { root.classList.add('theme-anim'); window.setTimeout(() => root.classList.remove('theme-anim'), 500) }
  root.dataset.theme = t
}

/** Light or dark. Starts from the saved choice, otherwise the system setting, and follows the system until you pick one. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || stored() || system())

  useEffect(() => {
    if (stored()) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => { if (stored()) return; const t = system(); setTheme(t); applyTheme(t) }
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next); applyTheme(next, true)
    try { localStorage.setItem(KEY, next) } catch { /* private mode: the choice just lasts for this visit */ }
  }, [theme])

  return { theme, toggle }
}
