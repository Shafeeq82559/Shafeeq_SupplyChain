import { RESP_HUE } from './chartkit'

export function RespChip({ r }: { r: string }) {
  return <span className="rchip" style={{ ['--h' as string]: RESP_HUE[r] ?? '#5c6e7c' }}>{r}</span>
}

export function Pips({ n, of = 5 }: { n: number; of?: number }) {
  return <span className="pips" aria-label={`${n} of ${of}`}>{Array.from({ length: of }, (_, i) => <i key={i} className={i < n ? 'on' : ''} />)}</span>
}
