// Shared chart palette and number formatting.
export const C = {
  sea: 'var(--sea)', sea2: 'var(--sea-2)', sky: '#5fb0cf', amber: 'var(--amber)', rust: 'var(--rust)', green: 'var(--green)', ink: 'var(--ink)',
  muted: 'var(--muted)', grid: 'var(--line)', violet: '#6a5acd', slate: '#8ba3b3',
}
export const SERIES = [C.sea, C.amber, C.green, C.rust, C.violet, C.sky]

export function signed(v: number, unit: string) {
  const a = Math.abs(v)
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${a >= 100 ? a.toFixed(0) : a.toFixed(1)} ${unit}`
}

export const RESP_HUE: Record<string, string> = {
  'Alternative Supplier': '#14506b', 'Production Reroute': '#9a6200', 'Inventory Buffer': '#2e7d5b', 'Customer Delay': '#a8321e', 'Combined Strategy': '#4a3f8f',
}

