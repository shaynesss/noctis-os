/* Light pooling round a card's edge -- a port of border-beam's
 * "pulse-outside" (MIT, Jakub Antalík), with the pools placed by us.
 *
 * The library paints eight pools at hand-picked spots on a 250px card,
 * which on a card five times wider leaves long stretches of edge dark.
 * The mechanism is worth keeping and the layout is not, so this is the
 * mechanism with the pools laid out evenly: five along the top, four along
 * the bottom, two up each side, and a soft glow in each corner.
 *
 * How it works, unchanged from the library: every pool is a radial ellipse
 * at a fixed point on the edge, painted three times -- a 1px stroke clipped
 * to the border, a blurred glow ten pixels outside it, and a wide bloom
 * thirty pixels out -- and a single 30fps loop eases each pool's width,
 * height, offset and opacity between two values on its own period, so no
 * two pools breathe together. Pools belong to one of three motion groups
 * and one of four opacity quadrants, the same way the library's do. */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export type PoolTone = 'silver' | 'faber'

// (x%, y%) on the edge; wide ellipses along the top and bottom, tall ones
// up the sides. `r` is the motion group, `q` the opacity quadrant.
type Pool = { x: string; y: string; w: number; h: number; r: 1 | 2 | 3; q: 'tl' | 'tr' | 'bl' | 'br' }
const POOLS: Pool[] = [
  { x: '10%', y: '0%', w: 110, h: 22, r: 1, q: 'tl' },
  { x: '30%', y: '-1%', w: 96, h: 16, r: 2, q: 'tl' },
  { x: '50%', y: '0%', w: 120, h: 20, r: 3, q: 'tr' },
  { x: '70%', y: '-1%', w: 96, h: 16, r: 1, q: 'tr' },
  { x: '90%', y: '0%', w: 110, h: 22, r: 2, q: 'tr' },
  { x: '100%', y: '30%', w: 22, h: 70, r: 3, q: 'tr' },
  { x: '101%', y: '70%', w: 24, h: 66, r: 1, q: 'br' },
  { x: '80%', y: '100%', w: 110, h: 20, r: 2, q: 'br' },
  { x: '60%', y: '101%', w: 96, h: 16, r: 3, q: 'br' },
  { x: '40%', y: '100%', w: 96, h: 16, r: 1, q: 'bl' },
  { x: '20%', y: '101%', w: 110, h: 20, r: 2, q: 'bl' },
  { x: '0%', y: '70%', w: 24, h: 66, r: 3, q: 'bl' },
  { x: '-1%', y: '30%', w: 22, h: 70, r: 1, q: 'tl' },
]
const CORNERS: [string, string, Pool['q']][] = [['0%', '0%', 'tl'], ['100%', '0%', 'tr'], ['0%', '100%', 'bl'], ['100%', '100%', 'br']]

// Greys the library uses for mono, cycled; Faber's red and a warmer
// neighbour for a build. Low alpha, so a colour reads as a tint of light.
const TONES: Record<PoolTone, string[]> = {
  silver: ['180, 180, 180', '190, 190, 190', '145, 145, 145', '165, 165, 165', '170, 170, 170', '140, 140, 140', '160, 160, 160'],
  faber: ['229, 51, 17', '240, 84, 40', '214, 46, 20', '229, 51, 17', '236, 70, 30'],
}

/** The pools as one background, with the loop's variables in it. `alpha`
 *  fixed (the bloom) or from the quadrant's oscillator (stroke and glow). */
function gradients(tone: PoolTone, scale: number, alpha?: number): string {
  const rgb = TONES[tone]
  const pools = POOLS.map((p, i) =>
    `radial-gradient(ellipse calc(${p.w * scale}px * var(--bw${p.r})) calc(${p.h * scale}px * var(--bh${p.r}) * var(--bgh))` +
    ` at calc(${p.x} + var(--bx${p.r})) calc(${p.y} + var(--by${p.r})),` +
    ` rgba(${rgb[i % rgb.length]}, ${alpha ?? `var(--bop-${p.q})`}), transparent)`)
  const corners = CORNERS.map(([x, y, q]) =>
    `radial-gradient(ellipse ${60 * scale}px ${60 * scale}px at ${x} ${y}, rgba(255, 255, 255, calc(0.18 * ${alpha ?? `var(--bop-${q})`})), transparent 70%)`)
  return [...pools, ...corners].join(', ')
}

// ------------------------------------------------------------ the loop

type Osc = { prop: string; a: number; b: number; period: number; delay: number; px: boolean }

/** The library's pulse-outside settings for a dark theme, on a 2.3s cycle:
 *  size swing, drift in px, opacity floor, height breathing, and periods. */
function oscillators(): Osc[] {
  const sp = 0.28, dr = 14, op = 0.46, gh = 0.16, bs = 2.3, ss = 6.4, ghs = 2.4
  return [
    { prop: '--bw1', a: 1 - sp, b: 1 + sp * 1.1, period: ss * 0.9, delay: 0, px: false },
    { prop: '--bh1', a: 1 + sp * 0.9, b: 1 - sp * 0.85, period: ss * 1.26, delay: 0, px: false },
    { prop: '--bx1', a: -dr, b: dr * 0.9, period: bs * 1.6, delay: 0, px: true },
    { prop: '--by1', a: dr * 0.55, b: -dr * 0.7, period: bs * 1.6, delay: 0, px: true },
    { prop: '--bw2', a: 1 + sp, b: 1 - sp * 0.85, period: ss * 1.1, delay: 0, px: false },
    { prop: '--bh2', a: 1 - sp * 0.8, b: 1 + sp * 1.05, period: ss * 0.81, delay: 0, px: false },
    { prop: '--bx2', a: dr * 0.8, b: -dr * 0.9, period: bs * 1.88, delay: 0, px: true },
    { prop: '--by2', a: -dr, b: dr * 0.65, period: bs * 1.88, delay: 0, px: true },
    { prop: '--bw3', a: 1 - sp * 0.6, b: 1 + sp * 1.15, period: ss * 0.98, delay: 0, px: false },
    { prop: '--bh3', a: 1 + sp * 0.75, b: 1 - sp, period: ss * 1.4, delay: 0, px: false },
    { prop: '--bx3', a: -dr * 0.6, b: dr, period: bs * 1.45, delay: 0, px: true },
    { prop: '--by3', a: -dr * 0.85, b: dr * 0.45, period: bs * 1.45, delay: 0, px: true },
    { prop: '--bgh', a: 1 - gh, b: 1 + gh, period: ghs, delay: 0, px: false },
    { prop: '--bop-tl', a: 1 - op, b: 1, period: bs, delay: 0, px: false },
    { prop: '--bop-tr', a: 1 - op, b: 1, period: bs * 1.32, delay: bs * 0.28, px: false },
    { prop: '--bop-bl', a: 1 - op, b: 1, period: bs * 0.84, delay: bs * 0.55, px: false },
    { prop: '--bop-br', a: 1 - op, b: 1, period: bs * 1.58, delay: bs * 0.83, px: false },
  ]
}
const OSC = oscillators()

// One loop for every instance on the page, 30fps, like the library's. A
// cosine ease between each oscillator's two values; the phase is the
// instance's own, so two cards never breathe in step.
const live = new Set<{ el: HTMLElement; phase: number }>()
let frame: number | null = null
let last = 0
const ease = (t: number) => (1 - Math.cos(Math.PI * 2 * t)) / 2
function tick(now: number) {
  frame = requestAnimationFrame(tick)
  if (now - last < 1000 / 30 - 2) return
  last = now
  const t = now / 1000
  for (const { el, phase } of live) {
    for (const o of OSC) {
      const v = o.a + (o.b - o.a) * ease((t + phase - o.delay) / o.period)
      el.style.setProperty(o.prop, o.px ? `${v.toFixed(2)}px` : v.toFixed(4))
    }
  }
}
function join(el: HTMLElement): () => void {
  const entry = { el, phase: Math.random() * 20 }
  live.add(entry)
  if (frame == null) frame = requestAnimationFrame(tick)
  return () => {
    live.delete(entry)
    if (live.size === 0 && frame != null) { cancelAnimationFrame(frame); frame = null }
  }
}

// ------------------------------------------------------- the component

/** Wrap a card. The card keeps its own border and background; the pools
 *  are painted on and around it. `radius` should match the card's. */
export function Pools({ tone = 'silver', radius = 4, strength = 1, children }: {
  tone?: PoolTone
  radius?: number
  /** 0–1, the whole effect's opacity. */
  strength?: number
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [on, setOn] = useState(false)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const leave = join(el)
    return leave
  }, [])
  // Fade in over 0.6s once mounted, as the library does, rather than
  // popping on with the page.
  useEffect(() => { const id = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(id) }, [])

  // Pools 1.6x the library's: on a card this wide, its sizes read as
  // thirteen separate blobs. Wider, each pool's tail meets the next and
  // the edge carries one soft band of light with brighter passages.
  const scale = 1.6
  const r = radius
  const layer: React.CSSProperties = { position: 'absolute', pointerEvents: 'none', transition: 'opacity 0.6s ease' }
  return (
    <div ref={ref} style={{ position: 'relative', isolation: 'isolate', '--bgh': 1, '--bop-tl': 1, '--bop-tr': 1, '--bop-bl': 1, '--bop-br': 1 } as React.CSSProperties}>
      {/* The bloom: wide, blurred, faint, behind everything. */}
      <div aria-hidden style={{
        ...layer, inset: -30, zIndex: -1, borderRadius: r + 30,
        background: gradients(tone, scale * 1.35, 0.77),
        filter: 'blur(24px) brightness(1.9) saturate(1.2)',
        transform: 'scale(0.95, 0.9)',
        opacity: on ? 0.11 * strength : 0,
      }} />
      {/* The glow: the pools ten pixels outside the edge, softened. */}
      <div aria-hidden style={{
        ...layer, inset: -10, zIndex: -1, borderRadius: r + 10,
        background: gradients(tone, scale),
        filter: 'blur(12px) brightness(1.3) saturate(1.2)',
        opacity: on ? 0.55 * strength : 0,
      }} />
      {children}
      {/* The stroke: the same pools clipped to the card's 1px edge. */}
      <div aria-hidden style={{
        ...layer, inset: 0, zIndex: 2, borderRadius: r, padding: 1,
        clipPath: `inset(0 round ${r}px)`,
        background: gradients(tone, scale),
        WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
        WebkitMaskComposite: 'xor',
        mask: 'linear-gradient(#fff 0 0) content-box exclude, linear-gradient(#fff 0 0)',
        filter: 'brightness(1.3) saturate(1.2)',
        opacity: on ? strength : 0,
      }} />
    </div>
  )
}
