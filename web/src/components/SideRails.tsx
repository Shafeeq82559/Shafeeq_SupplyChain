import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform, type MotionValue } from 'motion/react'
import { useMemo } from 'react'
import type { PageId } from './pages'
import { ease } from './motionkit'

/* Fixed illustrations either side of the content, on every page. They stay in view while scrolling and respond to it:
   the crane works as you read down the page, containers stack up, the ship sails and a container rides the route. */

const TINTS = ['#f2a900', '#1d7a9e', '#14506b', '#c2452d', '#8ba3b3', '#5fb0cf', '#f2a900', '#2e7d5b']

/** Page scroll progress 0..1, smoothed. Frozen at 0.5 when the user prefers reduced motion. */
function useProgress(): MotionValue<number> {
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll()
  const smooth = useSpring(scrollYProgress, { stiffness: 90, damping: 24, restDelta: 0.0005 })
  const still = useMotionValue(0.5)
  return reduce ? still : smooth
}

const STACK = (() => {
  const out: { x: number; y: number; c: string; at: number }[] = []
  let n = 0
  ;[0, 1, 2, 3].forEach((col) => [0, 1, 2].forEach((row) => { out.push({ x: 34 + col * 34, y: 292 - row * 19, c: TINTS[(col * 3 + row * 5 + 1) % TINTS.length], at: n++ }) }))
  ;[0, 1].forEach((col) => [0, 1].forEach((row) => { out.push({ x: 184 + col * 34, y: 292 - row * 19, c: TINTS[(col * 2 + row * 3 + 4) % TINTS.length], at: n++ }) }))
  return out
})()

function Box({ s, p }: { s: (typeof STACK)[number]; p: MotionValue<number> }) {
  const a = (s.at / STACK.length) * 0.85
  const opacity = useTransform(p, [a, a + 0.07], [0.18, 1])
  const y = useTransform(p, [a, a + 0.07], [-10, 0])
  return (
    <motion.g style={{ opacity, y }}>
      <rect x={s.x} y={s.y} width="31" height="17" rx="2" fill={s.c} fillOpacity=".88" />
      <path d={`M${s.x + 8} ${s.y}v17M${s.x + 16} ${s.y}v17M${s.x + 24} ${s.y}v17`} stroke="#fff" strokeOpacity=".35" strokeWidth="1" />
    </motion.g>
  )
}

function PortScene({ p }: { p: MotionValue<number> }) {
  const trolley = useTransform(p, [0, 1], [0, 120])
  const hoist = useTransform(p, [0, 0.2, 0.4, 0.6, 0.8, 1], [0, 74, 8, 74, 8, 74])
  const shipX = useTransform(p, [0, 1], [0, 64])
  const sway = useTransform(p, [0, 1], [-3, 3])
  const cable = useTransform(hoist, (v) => 50 + v)
  return (
    <svg className="rail-art" viewBox="0 0 290 660" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <g stroke="currentColor" strokeOpacity=".7" strokeWidth="3" fill="none" strokeLinecap="round">
        <path d="M52 52v240M232 52v240M52 52H262M20 76h70M52 100l30-24M232 100l-30-24M52 170h180" strokeWidth="2.2" />
        <path d="M20 52h110" strokeWidth="4" />
      </g>
      <motion.g style={{ x: trolley }}>
        <rect x="68" y="44" width="30" height="14" rx="3" fill="var(--ink)" />
        <motion.rect x="82.2" y="58" width="1.6" height={cable} fill="var(--ink)" fillOpacity=".75" />
        <motion.g style={{ y: hoist }}>
          <rect x="68" y="108" width="30" height="16" rx="2" fill="#f2a900" />
          <path d="M76 108v16M83 108v16M90 108v16" stroke="var(--ink)" strokeOpacity=".4" strokeWidth="1.2" />
        </motion.g>
      </motion.g>
      {STACK.map((s) => <Box key={s.at} s={s} p={p} />)}
      <line x1="10" y1="312" x2="280" y2="312" stroke="currentColor" strokeOpacity=".55" strokeWidth="2.5" />
      {[0, 1, 2, 3].map((i) => (
        <path key={i} d={`M0 ${352 + i * 28} q18 -10 36 0 t36 0 t36 0 t36 0 t36 0 t36 0 t36 0 t36 0 t36 0`} fill="none" stroke="#5fb0cf" strokeOpacity={0.55 - i * 0.1} strokeWidth="2"
          strokeDasharray="14 9" className="wave" style={{ animationDelay: `${i * -1.3}s` }} />
      ))}
      <motion.g style={{ x: shipX, rotate: sway, transformOrigin: '145px 420px', transformBox: 'view-box' }}>
        <g className="bob">
          {[0, 1, 2, 3, 4].map((i) => <rect key={i} x={48 + i * 31} y={420} width="28" height="16" rx="2" fill={TINTS[(i * 3 + 2) % TINTS.length]} fillOpacity=".9" />)}
          {[0, 1, 2, 3].map((i) => <rect key={i} x={64 + i * 31} y={403} width="28" height="16" rx="2" fill={TINTS[(i * 2 + 5) % TINTS.length]} fillOpacity=".9" />)}
          <rect x="204" y="386" width="26" height="50" rx="3" fill="var(--ink)" /><rect x="209" y="392" width="16" height="7" rx="1.5" fill="#5fb0cf" />
          <path d="M30 438h236l-22 32H56z" fill="var(--ink)" fillOpacity=".88" /><path d="M42 451h214" stroke="#c2452d" strokeWidth="3" />
        </g>
      </motion.g>
      <path d="M146 510C80 560 220 580 150 640" fill="none" stroke="currentColor" strokeOpacity=".5" strokeWidth="1.6" strokeDasharray="2 7" strokeLinecap="round" />
      <circle cx="150" cy="640" r="5" fill="var(--surface)" stroke="currentColor" strokeWidth="2.2" />
    </svg>
  )
}

const NODES: [number, number][] = [[50, 50], [220, 86], [110, 168], [236, 238], [58, 300], [160, 346], [244, 400], [90, 440]]
const LINKS = [[0, 1], [0, 2], [1, 3], [2, 3], [2, 4], [4, 5], [3, 5], [5, 6], [4, 7], [5, 7]]
const link = ([a, b]: number[]) => {
  const [x1, y1] = NODES[a], [x2, y2] = NODES[b]
  const mx = (x1 + x2) / 2 + (y2 - y1) * 0.18, my = (y1 + y2) / 2 - (x2 - x1) * 0.18
  return `M${x1} ${y1} Q${mx} ${my} ${x2} ${y2}`
}
// one long journey through the network that the scroll position drives
const JOURNEY = `${link([0, 1])} ${link([1, 3]).replace(/^M[\d.]+ [\d.]+ /, '')} ${link([3, 5]).replace(/^M[\d.]+ [\d.]+ /, '')} ${link([5, 6]).replace(/^M[\d.]+ [\d.]+ /, '')}`

function NetworkScene({ p }: { p: MotionValue<number> }) {
  const dist = useTransform(p, [0, 1], ['0%', '100%'])
  const reach = useTransform(p, [0, 1], [0, 1])
  const nodeAt = [0, 1, 3, 5, 6]
  return (
    <svg className="rail-art" viewBox="0 0 290 480" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeOpacity=".45" strokeWidth="1.6" strokeDasharray="2 7" strokeLinecap="round">
        {LINKS.map((l, i) => <path key={i} d={link(l)} className="route-dash" style={{ animationDelay: `${i * -2}s` }} />)}
      </g>
      <motion.path d={JOURNEY} fill="none" stroke="#1d7a9e" strokeWidth="2.6" strokeLinecap="round" style={{ pathLength: reach }} />
      {NODES.map(([x, y], i) => (
        <g key={i} transform={`translate(${x} ${y})`}>
          <circle r="6" fill="var(--surface)" stroke="currentColor" strokeWidth="2.4" />
          {nodeAt.includes(i) && <circle r="6" fill="none" stroke="#1d7a9e" strokeWidth="1.5" className="port-ping" style={{ animationDelay: `${i * 0.5}s` }} />}
        </g>
      ))}
      <motion.rect width="22" height="13" x="-11" y="-6.5" rx="2.5" fill="#f2a900" stroke="var(--ink)" strokeOpacity=".35" style={{ offsetPath: `path("${JOURNEY}")`, offsetDistance: dist, offsetRotate: 'auto' }} />
    </svg>
  )
}

const FACTS: Record<PageId, { n: string; t: string }[]> = {
  analyze: [{ n: '100,000', t: 'past disruptions searched' }, { n: '6', t: 'agents check every answer' }, { n: '5', t: 'response strategies compared' }],
  cases: [{ n: '100,000', t: 'cases in the index' }, { n: '3', t: 'ways to search: meaning, keywords or both' }, { n: '6', t: 'disruption types to filter by' }],
  prioritize: [{ n: '5', t: 'factors in every priority score' }, { n: '4', t: 'levels, from P1 critical to P4' }, { n: '0–100', t: 'score for each disruption' }],
  predict: [{ n: '6', t: 'outcomes predicted' }, { n: '80%', t: 'likely range around every estimate' }, { n: '5', t: 'strategies compared what-if' }],
  risk: [{ n: '6', t: 'disruption types weighed' }, { n: 'A to D', t: 'resilience grades' }, { n: '0–100', t: 'resilience score' }],
  evaluation: [{ n: '180', t: 'test searches scored' }, { n: '10', t: 'full answers graded by an LLM judge' }, { n: '20%', t: 'of the data held out to test the models' }],
  insights: [{ n: '100,000', t: 'records behind the charts' }, { n: '20%', t: 'of data held out to test the models' }, { n: '6', t: 'models predict the outcomes' }],
}

function Facts({ page, p }: { page: PageId; p: MotionValue<number> }) {
  const dash = useTransform(p, [0, 1], [0, 1])
  const pctText = useTransform(p, (v) => `${Math.round(v * 100)}%`)
  const facts = useMemo(() => FACTS[page], [page])
  return (
    <div className="rail-facts">
      <ul className="facts">
        {facts.map((f, i) => (
          <motion.li key={page + f.t} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 + i * 0.1, ease }}>
            <b className="num">{f.n}</b><span>{f.t}</span>
          </motion.li>
        ))}
      </ul>
      <div className="readprogress" title="How far down the page you are">
        <svg viewBox="0 0 36 36"><circle cx="18" cy="18" r="14" className="rp-track" /><motion.circle cx="18" cy="18" r="14" className="rp-bar" style={{ pathLength: dash }} /></svg>
        <motion.span className="num">{pctText}</motion.span>
        <small>of the page</small>
      </div>
    </div>
  )
}

export function SideRails({ page }: { page: PageId }) {
  const p = useProgress()
  const { scrollY } = useScroll()
  // on the Analyze page the hero is dark and full-bleed: let the illustrations arrive once you scroll past it
  const heroFade = useTransform(scrollY, (y) => (page === 'analyze' ? Math.min(Math.max((y - window.innerHeight * 0.55) / (window.innerHeight * 0.3), 0), 1) : 1))
  return (
    <div className="rails" aria-hidden="true">
      <motion.aside className="rail rail-l" style={{ opacity: heroFade }}><PortScene p={p} /></motion.aside>
      <motion.aside className="rail rail-r" style={{ opacity: heroFade }}><NetworkScene p={p} /><Facts page={page} p={p} /></motion.aside>
    </div>
  )
}
