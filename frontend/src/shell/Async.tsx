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
      Could not load {what}. The backend on{' '}
      <code className="font-mono text-[11.5px] text-ink-faint">localhost:8000</code> is not
      responding, or answered with an error.
      {/* Said out loud because it is true and was not visible: the panel
        * retries on its own, and the desktop app restarts a dead backend
        * within a few seconds. Without this line a panel that is actively
        * healing reads as a dead end, and the reasonable response is to
        * reload the window -- which throws away the session state that the
        * recovery was about to bring back. */}
      <div className="mt-[6px] text-ink-faint">
        Retrying automatically. If it does not come back, run{' '}
        <code className="font-mono text-[11.5px]">make doctor</code>.
      </div>
    </div>
  )
}
