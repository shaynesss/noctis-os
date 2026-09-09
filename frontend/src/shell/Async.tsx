/* Saying so when a route fails to load, and saying so when it fails.
 *
 * Shared because every panel needs the same three states, and the third is
 * the one that matters: an empty panel meaning "the backend is down" must
 * not look like one meaning "you have nothing".
 */


/** Shown wherever a panel's data could not be loaded. Says what failed and
 *  what to do about it, rather than rendering an empty state that looks like
 *  "you have no data" when it means "nothing was asked". */
export function Unreachable({ what }: { what: string }) {
  return (
    <div className="rounded-[3px] border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-dim">
      Could not load {what}. The backend is not responding on{' '}
      <code className="font-mono text-[11.5px] text-ink-faint">localhost:8000</code>.
    </div>
  )
}
