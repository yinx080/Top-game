import assert from 'node:assert/strict'
import { test } from 'node:test'
import { remainingSeconds } from '../src/lib/clock.ts'

test('todos cuentan el tiempo del servidor aunque sus relojes locales difieran', () => {
  const serverNow = 1800000000
  const deadline = serverNow + 90
  // Dos navegadores con distintos tiempos desde que arrancaron.
  assert.equal(remainingSeconds(deadline, serverNow, 100, 5100), 85)
  assert.equal(remainingSeconds(deadline, serverNow, 900000, 905000), 85)
  assert.equal(remainingSeconds(deadline, serverNow + 12, 200, 200), 78)
  assert.equal(remainingSeconds(serverNow + 10, serverNow, 100, 10101), 0)
  assert.equal(remainingSeconds(serverNow + 10, serverNow, 100, 21000), 0)
  // Un nuevo estado configura una duración nueva; no arrastra el contador anterior.
  assert.equal(remainingSeconds(serverNow + 300, serverNow, 100, 1100), 299)
})
