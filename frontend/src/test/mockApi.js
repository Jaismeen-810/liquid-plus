import { vi } from 'vitest'
import fx from './fixtures.json'

const ROUTES = [
  ['/api/auth/me', () => fx.me],
  ['/api/ingest/run-dates', () => fx.runDates],
  ['/api/ingest/batches', () => fx.batches],
  ['/api/ladder/deterministic/transactions', () => fx.txDet],
  ['/api/ladder/ai/transactions', () => fx.txAi],
  ['/api/ladder/deterministic', () => fx.det],
  ['/api/ladder/ai', () => fx.ai],
  ['/api/ladder/compare', () => fx.compare],
  ['/api/ml/predictions/', () => fx.rationale],
  ['/api/ml/models', () => fx.models],
  ['/api/recommendations', () => fx.recs],
  ['/api/analytics/exit-trends', () => fx.trends],
  ['/api/analytics/anomalies', () => fx.anomalies],
  ['/api/scenario/run', () => fx.scenario],
]

export const json = (body, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

export function mockApi(overrides = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(url => {
    const path = new URL(url).pathname
    if (overrides[path]) return overrides[path]()
    const route = ROUTES.find(([prefix]) => path.startsWith(prefix))
    return route ? json(route[1]()) : json({ error: { message: `No mock for ${path}` } }, 404)
  })
}

export { fx }
