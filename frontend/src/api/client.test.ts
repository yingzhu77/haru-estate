import { afterEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { api, ApiRequestError } from './client'

afterEach(() => vi.unstubAllGlobals())
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
