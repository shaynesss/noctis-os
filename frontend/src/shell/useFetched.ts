/* Loading a route, in three states.
 *
 * Its own module because a file exporting both a hook and a component breaks
 * fast refresh — and because the third state is the point: an empty panel
 * meaning "the backend is down" must not look like one meaning "you have
 * nothing".
 */
import { useEffect, useState } from 'react'
import { get } from './engine'

/** Fetch a route once on mount. `null` while loading, `false` when the
 *  request failed -- three states, because "loading" and "the backend is
 *  down" must not render the same way. */
/** How long to wait before trying a failed route again.
 *
 * Long enough not to hammer a backend that is genuinely down, short enough
 * that a restart -- which takes a second or two -- heals before it is worth
 * reaching for the window. */
const RETRY_MS = 3000

export function useFetched<T>(path: string): T | null | false {
  const [data, setData] = useState<T | null | false>(null)
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined

    const read = () => {
      void get<T>(path).then((d) => {
        if (!live) return
        setData(d ?? false)
        /* Keep trying while it is failing. The backend restarts on its own --
         * in development a single written file is enough -- and a panel that
         * stays broken until the window is reloaded makes a two-second blip
         * look like a permanent fault. Only failures retry; a route that
         * answered is done. */
        if (d == null) timer = setTimeout(read, RETRY_MS)
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
