import type { components } from './schema'
type S = components['schemas']
export type Project = S['Project']
export type Dataset = S['Dataset'] & { assumptions: S['Assumptions'] }
export type Phase = S['Phase']
export type Actual = S['Actual']
export type Contract = S['Contract']
export type Cost = S['Cost']
export type Assumptions = S['Assumptions']
export type Revision = Omit<S['Revision'], 'data'> & { data: Dataset }
export type Run = Omit<S['Run'], 'result'> & {
  members: S['Member'][]
  steps: S['Step'][]
  result?: ForecastResult | null
}
export type RunCreate = S['RunCreate']
export type Overrides = S['Overrides']
export type ForecastResult = S['ForecastResult'] & { scenario_totals: Record<string, string> }
export type MonthResult = S['MonthResult']
export type Member = S['Member']
export type Evidence = S['Evidence']
export type ImportPreview = S['ImportPreview']
export type Comparison = S['Comparison']
export type Source = S['Source']
export type RunPage = Omit<S['RunPage'], 'items'> & { items: Run[] }
export type RevisionPage = S['RevisionPage']
export type RevisionComparison = S['RevisionComparison']
