import { expect, it } from 'vitest'
import { formatBeijingTime } from './time'

it('converts UTC across midnight and respects an explicit offset', () => {
  expect(formatBeijingTime('2026-09-27T16:44:07.177798+00:00')).toBe('2026-09-28 00:44:07')
  expect(formatBeijingTime('2026-09-28T00:44:07+08:00')).toBe('2026-09-28 00:44:07')
  expect(formatBeijingTime('2026-12-31T16:00:00Z')).toBe('2027-01-01 00:00:00')
  expect(formatBeijingTime('invalid')).toBe('时间不可用')
})
