/* Light pooling round a card's edge -- after border-beam's "pulse-outside"
 * (MIT, Jakub Antalík), rebuilt for a wide card and a cheap frame.
 *
 * The look is the library's: soft pools of light at fixed points on the
 * edge, each breathing on its own, painted three times -- a 1px stroke
 * clipped to the border, a glow just outside it, and a wide faint bloom.
 * Two things are ours.
 *
 * The layout: the library fixes eight pools at spots chosen for a 250px
 * card; on a card five times wider that leaves long stretches of edge
 * dark. Thirteen pools sit here at even intervals -- five along the top,
 * four along the bottom, two up each side -- at the library's own size, so
 * each stays a distinct pool with dark edge between it and the next.
 *
 * The frame: the library paints every pool into one background of stacked
 * radial-gradients and moves them by rewriting custom properties, which
 * re-rasterises three full-card gradients thirty times a second and then
 * blurs two of them. On a 1240px card that stalled the interface. Here each
 * pool is its own element, painted once, and the loop touches only
 * `transform` and `opacity` -- compositor work, no repaint -- with the
 * softness in the gradient itself rather than a filter.
 *
 * Every pool is unique: its periods, drift, swing and phase come from its
 * own seed, so no two breathe alike, and each card starts at its own phase. */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export type PoolTone = 'silver' | 'faber'

// (x%, y%) on the edge; wide pools along the top and bottom, tall ones up
// the sides. Sizes are the library's, in px.
type Pool = { x: number; y: number; w: number; h: number }
const POOLS: Pool[] = [
  { x: 10, y: 0, w: 80, h: 19 }, { x: 30, y: -1, w: 74, h: 11 }, { x: 50, y: 0, w: 84, h: 13 },
  { x: 70, y: -1, w: 74, h: 11 }, { x: 90, y: 0, w: 80, h: 19 },
  { x: 100, y: 30, w: 15, h: 44 }, { x: 101, y: 70, w: 19, h: 38 },
  { x: 80, y: 100, w: 84, h: 13 }, { x: 60, y: 101, w: 60, h: 21 }, { x: 40, y: 100, w: 74, h: 11 }, { x: 20, y: 101, w: 84, h: 13 },
  { x: 0, y: 70, w: 17, h: 40 }, { x: -1, y: 30, w: 13, h: 32 },
]

// Greys the library uses for mono, cycled; Faber's red and warmer neighbours
// for a build. Low alpha, so a colour reads as a tint of light.
const TONES: Record<PoolTone, string[]> = {
  silver: ['180, 180, 180', '190, 190, 190', '145, 145, 145', '165, 165, 165', '170, 170, 170', '140, 140, 140', '160, 160, 160'],
  faber: ['229, 51, 17', '240, 84, 40', '214, 46, 20', '229, 51, 17', '236, 70, 30'],
}

/** A pool's own motion, from its index: periods in the library's ranges
 *  (size 4–9s, drift 2.5–5s, breath 1.8–4s), each nudged by a hash so no
 *  two pools share one, and a phase of its own. */
function motion(i: number, phase: number) {
  const h = (k: number) => (Math.sin((i + 1) * 12.9898 + k * 78.233) * 43758.5453) % 1  // deterministic, in [-1, 1)
  const u = (k: number) => Math.abs(h(k))
  return {
    sizeX: { period: 4.5 + u(1) * 4.5, swing: 0.2 + u(2) * 0.16, phase: phase + u(3) * 9 },
    sizeY: { period: 4 + u(4) * 5, swing: 0.2 + u(5) * 0.14, phase: phase + u(6) * 9 },
    driftX: { period: 2.6 + u(7) * 2.4, px: 8 + u(8) * 8, phase: phase + u(9) * 6 },
    driftY: { period: 2.8 + u(10) * 2.2, px: 6 + u(11) * 7, phase: phase + u(12) * 6 },
    breath: { period: 1.9 + u(13) * 2.2, floor: 0.5 + u(14) * 0.12, phase: phase + u(15) * 4 },
  }
}
type Motion = ReturnType<typeof motion>

// ------------------------------------------------------------ the loop

type Node = { el: HTMLElement; m: Motion }
const live = new Set<Node>()
let frame: number | null = null
let last = 0
const ease = (t: number) => (1 - Math.cos(Math.PI * 2 * t)) / 2      // 0→1→0, smooth
const wave = (t: number) => Math.cos(Math.PI * 2 * t)                 // -1→1
function tick(now: number) {
  frame = requestAnimationFrame(tick)
  if (now - last < 1000 / 30 - 2) return
  last = now
  const t = now / 1000
  for (const { el, m } of live) {
    const sx = 1 + m.sizeX.swing * wave((t + m.sizeX.phase) / m.sizeX.period)
    const sy = 1 + m.sizeY.swing * wave((t + m.sizeY.phase) / m.sizeY.period)
    const dx = m.driftX.px * wave((t + m.driftX.phase) / m.driftX.period)
    const dy = m.driftY.px * wave((t + m.driftY.phase) / m.driftY.period)
    const op = m.breath.floor + (1 - m.breath.floor) * ease((t + m.breath.phase) / m.breath.period)
    el.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px) scale(${sx.toFixed(3)}, ${sy.toFixed(3)})`
    el.style.opacity = op.toFixed(3)
  }
}
function join(nodes: Node[]): () => void {
  for (const n of nodes) live.add(n)
  if (frame == null && live.size) frame = requestAnimationFrame(tick)
  return () => {
    for (const n of nodes) live.delete(n)
    if (live.size === 0 && frame != null) { cancelAnimationFrame(frame); frame = null }
  }
}

// ------------------------------------------------------- the component

/** One layer of pools. `grow` scales the pools, `alpha` their peak. The
 *  gradient carries the softness: a radial falloff to transparent, so the
 *  glow and the bloom need no blur filter. */
function Layer({ tone, grow, alpha, style, mask }: {
  tone: PoolTone; grow: number; alpha: number; style: React.CSSProperties; mask?: React.CSSProperties
}) {
  const rgb = TONES[tone]
  // Only the stroke clips: its mask is the ring. The glow and the bloom sit
  // centred on the edge and must spill both ways -- clipped, each pool was
  // cut flat at the card's edge and read as a block rather than a light.
  return (
    <div aria-hidden style={{ position: 'absolute', pointerEvents: 'none', overflow: mask ? 'hidden' : 'visible', ...style, ...mask }}>
      {POOLS.map((p, i) => (
        <div key={i} data-pool={i} style={{
          position: 'absolute',
          left: `${p.x}%`, top: `${p.y}%`,
          width: p.w * grow, height: p.h * grow,
          marginLeft: -(p.w * grow) / 2, marginTop: -(p.h * grow) / 2,
          borderRadius: '50%',
          // A long falloff -- the softness that the library gets from a blur
          // filter, put into the paint instead so the frame stays cheap.
          background: `radial-gradient(closest-side, rgba(${rgb[i % rgb.length]}, ${alpha}) 0%, rgba(${rgb[i % rgb.length]}, ${alpha * 0.5}) 30%, rgba(${rgb[i % rgb.length]}, ${alpha * 0.15}) 62%, transparent 100%)`,
          willChange: 'transform, opacity',
        }} />
      ))}
    </div>
  )
}

/** Wrap a card. The card keeps its own border and background; the pools
 *  are painted on and around it. `radius` should match the card's. */
export function Pools({ tone = 'silver', radius = 8, strength = 1, children }: {
  tone?: PoolTone
  radius?: number
  /** 0–1, the whole effect's opacity. */
  strength?: number
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [on, setOn] = useState(false)
  useLayoutEffect(() => {
    const host = ref.current
    if (!host) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setOn(true); return }
    const phase = Math.random() * 20
    const nodes: Node[] = []
    host.querySelectorAll<HTMLElement>('[data-pool]').forEach((el) => {
      nodes.push({ el, m: motion(Number(el.dataset.pool), phase) })
    })
    const leave = join(nodes)
    const id = requestAnimationFrame(() => setOn(true))     // fade in, as the library does
    return () => { leave(); cancelAnimationFrame(id) }
  }, [])

  const r = radius
  const fade = (o: number): React.CSSProperties => ({ opacity: on ? o * strength : 0, transition: 'opacity 0.6s ease' })
  return (
    <div ref={ref} style={{ position: 'relative', isolation: 'isolate' }}>
      {/* Every layer is the card's own box, so a pool at "0%" is centred on
          the edge and spills both ways; the layers differ only in how big
          and how faint their pools are. (Inset layers put the pools ten and
          twenty pixels off the card, where they hovered as streaks.) The
          bloom is wide and faint, behind the card; the glow is just outside
          the edge. */}
      <Layer tone={tone} grow={2.4} alpha={0.5}
             style={{ inset: 0, zIndex: -1, ...fade(0.22) }} />
      <Layer tone={tone} grow={1.5} alpha={0.6}
             style={{ inset: 0, zIndex: -1, ...fade(0.6) }} />
      {children}
      {/* The stroke: the same pools clipped to the card's 1px edge. */}
      <Layer tone={tone} grow={1} alpha={0.9}
             style={{ inset: 0, zIndex: 2, borderRadius: r, ...fade(1) }}
             mask={{
               padding: 1,
               WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
               WebkitMaskComposite: 'xor',
               mask: 'linear-gradient(#fff 0 0) content-box exclude, linear-gradient(#fff 0 0)',
             }} />
    </div>
  )
}
