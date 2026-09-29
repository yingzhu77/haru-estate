import { describe, expect, it } from 'vitest'
import { isLocalEntry } from './deployment'

describe('administrator entry visibility', () => {
  it('offers local settings only on exact loopback hostnames', () => {
    for (const host of ['localhost', '127.0.0.1', '[::1]', '::1']) {
      expect(isLocalEntry(host)).toBe(true)
    }
    for (const host of ['demo.example.com', 'localhost.example.com', '192.168.1.2']) {
      expect(isLocalEntry(host)).toBe(false)
    }
  })
})
