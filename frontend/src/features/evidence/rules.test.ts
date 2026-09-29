import { describe, expect, it } from 'vitest'
import { ruleIdentifier, ruleLabel } from './rules'

describe('evidence rule labels', () => {
  it('uses a business-readable label for delivery revenue recognition', () => {
    expect(ruleLabel('delivery-recognition')).toBe('交付时确认收入')
    expect(ruleIdentifier('delivery-recognition')).toBe('内部追溯编号：delivery-recognition')
  })

  it('does not expose an unfamiliar saved rule identifier as the primary label', () => {
    expect(ruleLabel('older-snapshot-rule')).toBe('已保存的计算规则')
    expect(ruleIdentifier('older-snapshot-rule')).toBe('内部追溯编号：older-snapshot-rule')
  })
})
