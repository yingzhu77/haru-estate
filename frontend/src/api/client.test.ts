import { afterEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { api, ApiRequestError } from './client'

afterEach(() => vi.unstubAllGlobals())
it('uses a short inclusive range for 600 continuous evidence months', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({})))
  vi.stubGlobal('fetch', fetcher)
  const months = Array.from(
    { length: 600 },
    (_, i) => `${2026 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`,
  )
  await api.evidence('run', 'profit', undefined, months)
  const path = String(fetcher.mock.calls[0]?.[0])
  const params = new URL(path, 'http://localhost').searchParams
  expect(params.get('month_from')).toBe('2026-01')
  expect(params.get('month_to')).toBe('2075-12')
  expect(params.has('months')).toBe(false)
  expect(path.length).toBeLessThan(150)
})

it('preserves gaps in a non-continuous evidence selection', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({})))
  vi.stubGlobal('fetch', fetcher)
  await api.evidence('run', 'profit', undefined, ['2026-03', '2026-01', '2026-03'])
  const params = new URL(String(fetcher.mock.calls[0]?.[0]), 'http://localhost').searchParams
  expect(params.getAll('months')).toEqual(['2026-01', '2026-03'])
  expect(params.has('month_from')).toBe(false)
})

describe('mutation retry contract', () => {
  it('reuses the key after a lost response, then starts a fresh operation after success', async () => {
    vi.stubGlobal('crypto', webcrypto)
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('network lost'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'project-a' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'project-b' })))
    vi.stubGlobal('fetch', fetcher)
    const body = { name: 'retry simulation', template: 'demo' as const }
    await expect(api.createProject(body)).rejects.toThrow('network lost')
    await api.createProject(body)
    await api.createProject(body)
    const keys = fetcher.mock.calls.map((call) =>
      new Headers(call[1].headers).get('Idempotency-Key'),
    )
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
    expect(keys[2]).not.toBe(keys[1])
  })

  it('preserves structured conflict information and starts a new key after a definitive rejection', async () => {
    vi.stubGlobal('crypto', webcrypto)
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ code: 'CONFLICT', message: '版本变化', request_id: 'request-42' }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'revision' })))
    vi.stubGlobal('fetch', fetcher)
    const body = { name: 'renamed', base_version: 1, archived: false }
    const error = await api.patchProject('p', body).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(ApiRequestError)
    expect(error).toMatchObject({ status: 409, code: 'CONFLICT', requestId: 'request-42' })
    expect((error as Error).message).toContain('request-42')
    await api.patchProject('p', body)
    const keys = fetcher.mock.calls.map((call) =>
      new Headers(call[1].headers).get('Idempotency-Key'),
    )
    expect(keys[1]).not.toBe(keys[0])
  })

  it('sends exact scope and server filters rather than filtering the latest global page', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify([])))
    vi.stubGlobal('fetch', fetcher)
    await api.runs(undefined, ['b', 'a'], 'portfolio')
    const params = new URL(String(fetcher.mock.calls[0]?.[0]), 'http://localhost').searchParams
    expect(params.get('scope_ids')).toBe('a,b')
    expect(params.get('kind')).toBe('portfolio')
  })
})
