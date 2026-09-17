/* Noctis wordmark — the name, set rather than drawn.
 *
 * Five letters of Cascadia Code and one star. The star stands where the O
 * would be and occupies exactly `1ch`, one monospace cell, so the letter
 * rhythm survives the substitution: the word is the interface's own face
 * with a single glyph swapped, not a picture of a word placed next to it.
 *
 * It was drawn first, on its own geometric grid, and read as a foreign
 * object in a column of Cascadia (2026-09-17) -- different proportions,
 * different stroke logic, different rhythm. Two things followed from that,
 * and the second is less obvious: a solid SVG stroke at `--color-ink`
 * renders *brighter* than antialiased text at the same hex, because text is
 * softened at every edge and a filled path is not. The mark was lighter
 * than its neighbours twice over, being both solid and a step up the ramp
 * from the dim grey most of this interface actually speaks in.
 *
 * So: `--color-ink-dim`, weight 400, set by the caller. The star is the
 * same path as `Logo.tsx` rather than a redrawing of it, so the mark in the
 * name and the mark everywhere else are one shape.
 */
export function Wordmark({
  size = 15,
  className = '',
  style,
}: {
  /** Font size in px. The word is six cells wide, so it grows from here. */
  size?: number
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <span
      role="img"
      aria-label="Noctis"
      className={`font-mono ${className}`}
      style={{ fontSize: size, letterSpacing: '0.06em', whiteSpace: 'nowrap', ...style }}
    >
      N
      <svg
        viewBox="0 0 24 24"
        aria-hidden
        className="inline-block w-[1ch] align-[-0.1em]"
        style={{ height: '0.88em' }}
      >
        <path
          d="M12 0 Q12.7 9.3 21.5 12 Q12.7 14.7 12 24 Q11.3 14.7 2.5 12 Q11.3 9.3 12 0 Z"
          fill="currentColor"
        />
      </svg>
      CTIS
    </span>
  )
}
