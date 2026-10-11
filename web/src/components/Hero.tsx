import { motion, useScroll, useTransform } from 'motion/react'

const LINES = ['AI Powered', 'Supply Chain', 'Disruption Assistant']

// Three trade routes crossing the screen; containers sail along them, ports pulse where routes meet.
const ROUTES = [
  'M-60 650 C 300 430, 600 780, 980 530 S 1500 300, 1700 390',
  'M-60 310 C 250 170, 640 340, 900 220 S 1400 130, 1700 210',
  'M180 960 C 420 710, 860 830, 1100 650 S 1500 570, 1700 710',
]
const PORTS: [number, number][] = [[980, 530], [900, 220], [1100, 650], [330, 400], [1380, 330]]

function Backdrop() {
  const reduce = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const grat = Array.from({ length: 14 }, (_, i) => `M${i * 130 - 40} -20 Q${i * 130 + 30} 450 ${i * 130 - 50} 920`)
  return (
    <svg className="hero-art" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <g fill="none" stroke="#6f8b9b" strokeOpacity=".16" strokeWidth="1">{grat.map((d) => <path key={d} d={d} />)}</g>
      <g fill="none" strokeLinecap="round">
        {ROUTES.map((d, i) => (
          <g key={d}>
            <path d={d} stroke="#2b6985" strokeOpacity=".55" strokeWidth="1.5" strokeDasharray="2 9" className="route-dash" style={{ animationDelay: `${i * -2}s` }} />
            {!reduce && [0, 1].map((k) => (
              <rect key={k} width="22" height="13" x="-11" y="-6.5" rx="2" fill="#f2a900" fillOpacity=".9">
                <animateMotion dur={`${22 + i * 5}s`} begin={`${-k * (11 + i * 2.5)}s`} repeatCount="indefinite" path={d} rotate="auto" />
              </rect>
            ))}
          </g>
        ))}
      </g>
      {PORTS.map(([x, y], i) => (
        <g key={i} transform={`translate(${x} ${y})`}>
          <circle r="5" fill="#0e1b28" stroke="#5fb0cf" strokeWidth="2" />
          <circle r="5" fill="none" stroke="#5fb0cf" strokeWidth="1.5" className="port-ping" style={{ animationDelay: `${i * 0.7}s` }} />
        </g>
      ))}
    </svg>
  )
}

export function Hero() {
  const { scrollY } = useScroll()
  const y = useTransform(scrollY, [0, 520], [0, -110])
  const fade = useTransform(scrollY, [0, 420], [1, 0])
  const scale = useTransform(scrollY, [0, 520], [1, 0.94])
  const art = useTransform(scrollY, [0, 700], [0, 90])

  return (
    <section className="hero" aria-labelledby="hero-title">
      <motion.div className="hero-art-wrap" style={{ y: art }}><Backdrop /></motion.div>
      <motion.div className="hero-inner" style={{ y, opacity: fade, scale }}>
        <h1 id="hero-title" className="hero-title" aria-label={LINES.join(' ')}>
          {LINES.map((l, i) => (
            <span key={l} className="hero-line" aria-hidden="true"><span style={{ ['--i' as string]: i }}>{l}</span></span>
          ))}
        </h1>
        <p className="hero-sub">Describe what broke. Six agents check it against 100,000 past disruptions, estimate the damage and recovery time, and recommend a response you can defend.</p>
      </motion.div>
      <a className="scroll-cue" href="#begin" onClick={(e) => { e.preventDefault(); document.getElementById('begin')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}>
        <span>Scroll to start</span><i />
      </a>
    </section>
  )
}
