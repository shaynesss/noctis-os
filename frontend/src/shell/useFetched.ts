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
export function useFetched<T>(path: string): T | null | false {
  const [data, setData] = useState<T | null | false>(null)
  useEffect(() => {
    let live = true
    void get<T>(path).then((d) => live && setData(d ?? false))
    return () => {
      live = false
    }
  }, [path])
  return data
}
