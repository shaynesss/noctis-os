/* Noctis wordmark — the name, drawn.
 *
 * Six letters on one grid: cap height 12, letter box 8, advance 11, stroked
 * at 1.7 so the word carries the same weight as the rail icons beside it.
 * The O is the app's own star, and it is the *same path* as `Logo.tsx`
 * rather than a redrawing of it, so the mark in the name and the mark
 * everywhere else are one shape.
 *
 * Drawn rather than set, for three reasons that only a wordmark gets to
 * claim: there is no font to load before the app can say its own name, no
 * fallback face to flash on a cold start, and no trailing letter-space to
 * compensate for (the text version sat a fraction left of centre because
 * CSS tracks after the final letter as well as between).
 *
 * Takes `currentColor`. It is plain ink in the rail; a caller that wants it
 * to carry the session's accent only has to set a colour.
 */
export function Wordmark({
  width = 88,
  className = '',
  style,
}: {
  width?: number
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <svg
      viewBox="0 0 65.4 16"
      width={width}
      height={(width * 16) / 65.4}
      role="img"
      aria-label="Noctis"
      className={className}
      style={{ display: 'block', ...style }}
    >
      <title>Noctis</title>
      {/* N, C, T, I, S. The O's slot is left empty for the star. */}
      <path
        d="M1.2,14.0 V2.0 L9.2,14.0 V2.0 M29.66,3.27 A4.00,6.00 0 1 0 29.66,12.73 M34.2,2.0 H42.2 M38.2,2.0 V14.0 M46.800000000000004,2.0 H51.6 M49.2,2.0 V14.0 M46.800000000000004,14.0 H51.6 M63.6,4.2 C63.6,2.6 61.800000000000004,2.0 60.2,2.0 C57.800000000000004,2.0 56.400000000000006,3.1 56.400000000000006,4.8 C56.400000000000006,6.6 58.2,7.4 60.2,8.0 C62.2,8.6 64.0,9.4 64.0,11.2 C64.0,12.9 62.6,14.0 60.2,14.0 C58.6,14.0 56.800000000000004,13.4 56.800000000000004,11.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* The star, a little past the cap height: it is a mark standing in
          for a letter, not a letter. */}
      <g transform="translate(9.60 1.40) scale(0.5500)">
        <path d="M12 0 Q12.7 9.3 21.5 12 Q12.7 14.7 12 24 Q11.3 14.7 2.5 12 Q11.3 9.3 12 0 Z" fill="currentColor" />
      </g>
    </svg>
  )
}
