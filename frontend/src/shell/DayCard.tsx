/* The Activity grid's day card (2026-10-01).
 *
 * Replaces the native `title` tooltip, which macOS shows after a second's
 * wait and draws in its own grey, nothing to do with the app. This one is
 * there the moment the pointer lands, in the app's own sheet and type, and
 * glides from day to day as the pointer moves along the grid.
 *
 * Rendered into document.body: the Stats card it belongs to sits inside the
 * border beam, whose pools move by transform, and a fixed-position element
 * inside a transformed ancestor is positioned against that ancestor instead
 * of the window. */
import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ModeMark } from './Chrome'
import { MODE_LABEL, type Mode } from './domain'
import { cardDate, compactTokens, dayStory, relativeDay } from './grid'

export interface DayCardData {
  date: Date
  sessions: number
  tokens: number
  modes: Partial<Record<Mode, number>>
  /** The busiest day's tokens in the visible year, for the bar. */
  maxTokens: number
  streak: number
  /** The hovered cell, in window coordinates. */
  anchor: DOMRect
}

const GAP = 10

export function DayCard({ day, today }: { day: DayCardData; today: Date }) {
  const card = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(236)
  useLayoutEffect(() => {
    if (card.current) setWidth(card.current.offsetWidth)
  }, [day.sessions, day.tokens, day.streak])

  const { lead, line } = dayStory(day.date, day.modes)
  const when = relativeDay(day.date, today)
  const share = day.maxTokens ? day.tokens / day.maxTokens : 0
  const busiest = day.tokens > 0 && day.tokens === day.maxTokens
  const present = (Object.entries(day.modes) as [Mode, number][])
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])

  // Centred above the cell, kept inside the window, and below it when there
  // is no room above (the top rows of a short window).
  const half = width / 2
  const x = Math.min(Math.max(day.anchor.left + day.anchor.width / 2, half + 8), window.innerWidth - half - 8)
  const above = day.anchor.top > 150
  const y = above ? day.anchor.top - GAP : day.anchor.bottom + GAP

  return createPortal(
    <div role="status" aria-live="polite"
         className="pointer-events-none fixed left-0 top-0 z-[70]"
         style={{
           transform: `translate3d(${x}px, ${y}px, 0) translate(-50%, ${above ? '-100%' : '0'})`,
           transition: 'transform 90ms cubic-bezier(0.22, 1, 0.36, 1)',
         }}>
      <div ref={card} key={`${day.date.toDateString()}`}
           className="day-card w-[236px] rounded-sheet border border-line bg-sheet px-[13px] py-[11px] font-mono shadow-[0_14px_36px_rgba(0,0,0,0.5)]">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[11.5px] text-ink">{cardDate(day.date)}</span>
          {when && <span className="text-[10px]" style={{ color: 'var(--sig-text)' }}>{when}</span>}
        </div>

        <div className="mt-[8px] flex items-baseline gap-[10px] tabular-nums">
          <span className="text-[13px] text-ink">
            <b className="font-semibold">{day.sessions}</b>
            <span className="text-ink-faint"> session{day.sessions === 1 ? '' : 's'}</span>
          </span>
          {day.tokens > 0 && (
            <span className="text-[12px] text-ink-dim">{compactTokens(day.tokens)} <span className="text-ink-faint">tokens</span></span>
          )}
        </div>

        {day.tokens > 0 && (
          <div className="mt-[8px]">
            <div className="h-[3px] overflow-hidden rounded-full" style={{ background: 'rgba(255,255,255,0.07)' }}>
              <div className="h-full rounded-full"
                   style={{ width: `${Math.max(3, Math.round(share * 100))}%`, background: busiest ? 'var(--sig-fill-max)' : 'var(--sig-fill)' }} />
            </div>
            <div className="mt-[4px] text-[9.5px] text-ink-faint">
              {busiest ? <span style={{ color: 'var(--sig-text)' }}>✦ busiest day of the year</span> : `${Math.round(share * 100)}% of the busiest day`}
            </div>
          </div>
        )}

        <div className="mt-[10px] flex items-center gap-[8px] border-t border-line pt-[9px]">
          {lead
            ? <span key={`${lead}-${day.date.toDateString()}`} className="day-card-hop inline-flex"><ModeMark mode={lead} size={18} /></span>
            : <span className="inline-flex opacity-60"><ModeMark mode="noctua" size={18} dim /></span>}
          <span className="text-[11px] text-ink-dim">{line}</span>
        </div>

        {present.length > 0 && (
          <div className="mt-[7px] flex flex-wrap items-center gap-x-[10px] gap-y-[4px]">
            {present.map(([m, n]) => (
              <span key={m} className="inline-flex items-center gap-[4px] text-[10px] text-ink-faint" title={MODE_LABEL[m]}>
                <ModeMark mode={m} size={12} dim={m !== lead} />
                <span className="tabular-nums">{n}</span>
              </span>
            ))}
            {day.streak >= 3 && (
              <span className="ml-auto text-[10px]" style={{ color: 'var(--sig-text)' }}>{day.streak}-day streak</span>
            )}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
