/* Noctis mark — a four-point star.
 *
 * Taken from a diffraction-spike reference: the distinctive part is not the
 * star itself but its *asymmetry* — a long vertical spike, a shorter
 * horizontal one, both tapering to hairlines from a bright core. A symmetric
 * sparkle reads as decoration; the elongated one reads as a point of light,
 * which is the right note for a system named for the night.
 *
 * Drawn rather than imported so it takes `currentColor` — the mark then
 * carries the active mode's accent, which makes it a live element rather
 * than a static badge sitting above a UI that changes around it.
 */
export function Logo({
  size = 16,
  className = '',
  style,
}: {
  size?: number
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden
      className={className}
      style={{ display: 'block', overflow: 'visible', ...style }}
    >
      {/* The spikes proper. Concave sides via quadratic curves, so the taper
          is a curve rather than a straight-edged diamond — that concavity is
          what makes it read as light rather than as a geometric star. */}
      <path
        d="M12 0 Q12.7 9.3 21.5 12 Q12.7 14.7 12 24 Q11.3 14.7 2.5 12 Q11.3 9.3 12 0 Z"
        fill="currentColor"
      />
      {/* Hairline continuation past the body, at low opacity. The reference's
          spikes run the whole frame; at 16px a full-length line would be
          noise, so this is a hint of that rather than a copy of it. */}
      <path
        d="M12 -6 V30 M-4 12 H28"
        stroke="currentColor"
        strokeWidth="0.5"
        opacity="0.35"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
