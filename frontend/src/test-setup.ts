/* No test reaches the network (2026-09-30).
 *
 * The frontend tests run with the real .env, so `engine`'s helpers point at
 * the live backend with a real token. When `rememberSlots` began sending the
 * arrangement to the backend, a test that called it overwrote the real saved
 * tabs with its fixtures on every run, and a switch to the packaged app would
 * have opened on two fake tabs. The backend suite has had this protection
 * since July (conftest's isolated vault and history); this is the frontend's.
 *
 * Every real fetch is refused and recorded, and the test that made it fails
 * with the address it tried. A test that means to talk to "the network"
 * replaces fetch itself, as engine.test.ts does. */
import { afterEach } from 'vitest'

const reached: string[] = []

globalThis.fetch = ((input: RequestInfo | URL) => {
  reached.push(String(input instanceof Request ? input.url : input))
  return Promise.reject(new TypeError('a test tried to reach the network'))
}) as typeof fetch

afterEach(() => {
  if (reached.length) {
    const tried = reached.splice(0)
    throw new Error(`a test reached the network: ${tried.join(', ')}`)
  }
})
