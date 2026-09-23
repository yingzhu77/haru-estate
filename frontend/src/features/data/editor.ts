import type { Actual, Dataset, Revision } from '../../api/types'

export const metricLabels: Record<Actual['metric'], string> = {
  sales: '销售签约',
  collections: '回款',
  revenue: '确认收入',
  cogs: '结转成本',
  development: '开发投入',
  payments: '成本付款',
  expenses: '费用确认',
  expense_payments: '费用付款',
  taxes: '税费确认',
  tax_payments: '税费付款',
  interest: '利息',
  borrowing: '借款到账',
  repayment: '偿还本金',
}
export const runLabels: Record<string, string> = {
  queued: '排队中',
  running: '计算中',
  completed: '已完成',
  succeeded: '已完成',
  failed: '失败',
  interrupted: '中断待恢复',
  incomplete: '汇总未完成',
  waiting: '等待成员完成',
}
export const scenarioLabels: Record<string, string> = {
  base: '基准',
  optimistic: '乐观',
  prudent: '审慎',
}
export function cloneData(data: Dataset): Dataset {
  return JSON.parse(JSON.stringify(data)) as Dataset
}
// Draft bases outlive this page, so returning to a draft never silently rebases it.
export const draftBases: Record<string, Revision> = {}
export function isDirty(data: Dataset | undefined, base: Revision | undefined) {
  return !!data && !!base && JSON.stringify(data) !== JSON.stringify(base.data)
}
export function phaseReferenced(data: Dataset, id: string) {
  return [...(data.contracts ?? []), ...(data.costs ?? []), ...(data.actuals ?? [])].some(
    (row) => row.phase_id === id,
  )
}
export interface EditorField {
  key: string
  label: string
  type?: 'month' | 'date' | 'number' | 'phase' | 'category' | 'metric'
}
export const collectionFields: Record<'phases' | 'contracts' | 'costs' | 'actuals', EditorField[]> =
  {
    phases: [
      { key: 'id', label: '分期编号' },
      { key: 'name', label: '名称' },
      { key: 'area', label: '总可售面积（㎡）' },
      { key: 'price', label: '未售单价（元/㎡）' },
      { key: 'sales_start', label: '销售开始', type: 'month' },
      { key: 'sales_months', label: '去化月数', type: 'number' },
      { key: 'delivery_month', label: '交付月份', type: 'month' },
      { key: 'known_on', label: '信息获知日期', type: 'date' },
    ],
    contracts: [
      { key: 'id', label: '合同编号' },
      { key: 'phase_id', label: '所属分期', type: 'phase' },
      { key: 'sale_month', label: '签约月份', type: 'month' },
      { key: 'area', label: '面积（㎡）' },
      { key: 'amount', label: '签约金额（元）' },
      { key: 'known_on', label: '信息获知日期', type: 'date' },
      { key: 'recognized_month', label: '已确认收入月份（可空）', type: 'month' },
    ],
    costs: [
      { key: 'id', label: '成本编号' },
      { key: 'phase_id', label: '所属分期', type: 'phase' },
      { key: 'category', label: '成本类别', type: 'category' },
      { key: 'amount', label: '成本总额（元）' },
      { key: 'incurred_month', label: '发生/计划发生月份', type: 'month' },
      { key: 'known_on', label: '信息获知日期', type: 'date' },
    ],
    actuals: [
      { key: 'id', label: '实际记录编号' },
      { key: 'phase_id', label: '所属分期', type: 'phase' },
      { key: 'month', label: '业务月份', type: 'month' },
      { key: 'known_on', label: '信息获知日期', type: 'date' },
      { key: 'metric', label: '指标', type: 'metric' },
      { key: 'amount', label: '金额（元）' },
      { key: 'contract_id', label: '关联回款合同编号（可空）' },
      { key: 'note', label: '备注' },
    ],
  }
export const assumptionFields: EditorField[] = [
  { key: 'opening_month', label: '模型开始月份', type: 'month' },
  { key: 'opening_cash', label: '期初现金（元）' },
  { key: 'monthly_overhead', label: '月度管理费用（元）' },
  { key: 'marketing_rate', label: '营销费率（小数，如 0.02）' },
  { key: 'tax_rate', label: '简化税费率（小数）' },
  { key: 'down_payment_rate', label: '首付比例（小数）' },
  { key: 'collection_lag', label: '尾款滞后（月）', type: 'number' },
  { key: 'expense_payment_lag', label: '费用付款滞后（月）', type: 'number' },
  { key: 'loan_limit', label: '融资额度（元）' },
  { key: 'annual_interest_rate', label: '年利率（小数）' },
]
