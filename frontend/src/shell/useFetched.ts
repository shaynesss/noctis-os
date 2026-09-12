/* Loading a route, in three states.
 *
 * Its own module because a file exporting both a hook and a component breaks
 * fast refresh — and because the third state is the point: an empty panel
 * meaning "the backend is down" must not look like one meaning "you have
 * nothing".
 */
import { useEffect, useState } from 'react'
import { get } from './engine'

/** How long to wait before trying a failed route again.
 *
 * Growing, not fixed. The first delay is short because the common case is a
 * restart that takes a second or two and should heal before it is worth
 * reaching for the window. The later ones are long because the other case is
 * a backend that is genuinely down, and a panel polling it every three
 * seconds forever is a busy loop against a machine that has already said no
 * -- the same reason a supervisor backs off rather than restarting flat out.
 *
 * It never stops entirely, unlike the watchdog, and the asymmetry is
 * deliberate: retrying costs one request against localhost, while restarting
 * a process that will not stay up costs a thrash that hides the fault. */
const RETRY_MS = [1000, 2000, 4000, 8000, 15000]

const backoff = (attempt: number) =>
  RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)]

/** Fetch a route, retrying while it fails. `null` while loading, `false`
 *  when the last attempt failed -- three states, because "loading" and "the
 *  backend is down" must not render the same way. */
export function useFetched<T>(path: string): T | null | false {
  const [data, setData] = useState<T | null | false>(null)
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0

    const read = () => {
      void get<T>(path).then((d) => {
        if (!live) return
        setData(d ?? false)
        /* Keep trying while it is failing. The backend restarts on its own --
         * in development a single written file is enough -- and a panel that
         * stays broken until the window is reloaded makes a two-second blip
         * look like a permanent fault. Only failures retry; a route that
         * answered is done. */
        if (d == null) {
          timer = setTimeout(read, backoff(attempt))
          attempt += 1
        } else {
          attempt = 0
        }
      })
    }
    read()

    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [path])
  return data
}
