const rules = {
  'opening-balance': '期初现金余额',
  'historical-actual': '历史实际记录',
  'future-cost': '未来开发投入',
  'cost-payment': '成本付款计划',
  'signed-contract': '已签合同金额',
  'contract-collection': '合同回款节点',
  'unsold-sales-plan': '未售销售计划',
  'down-payment': '新增销售首付款',
  'remaining-collection': '新增销售尾款及按揭回款',
  'delivery-recognition': '交付时确认收入',
  'area-cost-allocation': '按面积结转成本',
  'fixed-and-sales-fees': '固定管理费与营销费',
  'expense-payment': '费用付款安排',
  'illustrative-tax': '模拟税费计提',
  'tax-payment': '模拟税费缴付',
  'opening-loan-interest': '期初借款利息',
  'limited-financing': '融资额度内提款',
  'scheduled-repayment': '计划归还借款本金',
} as const

export function ruleLabel(rule: string): string {
  return rules[rule as keyof typeof rules] ?? '已保存的计算规则'
}

export function ruleIdentifier(rule: string): string {
  return `内部追溯编号：${rule}`
}
