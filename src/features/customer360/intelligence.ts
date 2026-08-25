import type { CustomerSummary } from './types'

export type ScoreFactor = { label: string; score: number; weight: number; explanation: string }
export type HealthResult = { score: number; status: 'Excellent'|'Good'|'Watch'|'High Risk'|'Critical'; factors: ScoreFactor[] }
export type Recommendation = { id: string; title: string; reason: string; impact: 'High'|'Medium'|'Low'; action: string }

const clamp = (value:number) => Math.max(0, Math.min(100, Math.round(value)))

export function calculateHealth(customer: CustomerSummary): HealthResult {
  const utilization = customer.credit.utilization_percent ?? 0
  const utilizationScore = utilization <= 60 ? 100 : utilization <= 75 ? 90 : utilization <= 90 ? 70 : utilization <= 100 ? 45 : 20
  const pastDueRatio = customer.credit.total_exposure > 0 ? customer.aging.past_due / customer.credit.total_exposure : 0
  const paymentScore = customer.aging.past_due <= 0 ? 100 : pastDueRatio < .1 ? 80 : pastDueRatio < .25 ? 55 : 25
  const salesGrowth = customer.sales.last_year > 0 ? ((customer.sales.year_to_date - customer.sales.last_year) / customer.sales.last_year) * 100 : 0
  const salesScore = salesGrowth >= 10 ? 100 : salesGrowth >= 0 ? 85 : salesGrowth >= -10 ? 60 : 35
  const relationshipScore = customer.general.active ? 90 : 35
  const riskScore = customer.credit.available_credit >= 0 && customer.aging.days_90 + customer.aging.days_120 <= 0 ? 95 : customer.credit.available_credit < 0 ? 30 : 60

  const factors: ScoreFactor[] = [
    { label: 'Credit', score: utilizationScore, weight: .30, explanation: `${utilization.toFixed(1)}% of the credit line is currently utilized.` },
    { label: 'Payment', score: paymentScore, weight: .30, explanation: `${customer.aging.past_due.toLocaleString('en-US', {style:'currency', currency:'USD'})} is past due.` },
    { label: 'Sales', score: salesScore, weight: .20, explanation: `Year-to-date sales trend is ${salesGrowth.toFixed(1)}% versus the comparison period.` },
    { label: 'Relationship', score: relationshipScore, weight: .10, explanation: customer.general.active ? 'The customer account is active.' : 'The customer account is inactive.' },
    { label: 'Risk', score: riskScore, weight: .10, explanation: customer.credit.available_credit < 0 ? 'Total exposure exceeds the approved credit line.' : 'Exposure remains within the approved credit line.' },
  ]
  const score = clamp(factors.reduce((sum, factor) => sum + factor.score * factor.weight, 0))
  const status = score >= 90 ? 'Excellent' : score >= 75 ? 'Good' : score >= 60 ? 'Watch' : score >= 40 ? 'High Risk' : 'Critical'
  return { score, status, factors }
}

export function buildRecommendations(customer: CustomerSummary, health: HealthResult): Recommendation[] {
  const items: Recommendation[] = []
  const utilization = customer.credit.utilization_percent ?? 0
  const growth = customer.sales.last_year > 0 ? ((customer.sales.year_to_date - customer.sales.last_year) / customer.sales.last_year) * 100 : 0
  if (customer.credit.available_credit < 0) items.push({id:'over-limit', title:'Review account exposure', reason:`Exposure exceeds the credit line by ${Math.abs(customer.credit.available_credit).toLocaleString('en-US',{style:'currency',currency:'USD'})}.`, impact:'High', action:'Open credit review'})
  else if (utilization >= 90) items.push({id:'utilization', title:'Review available credit', reason:`Credit utilization is ${utilization.toFixed(1)}%.`, impact:'High', action:'Review credit line'})
  if (customer.aging.past_due > 0) items.push({id:'past-due', title:'Review past-due invoices', reason:`The account has ${customer.aging.past_due.toLocaleString('en-US',{style:'currency',currency:'USD'})} past due.`, impact: customer.aging.days_90 + customer.aging.days_120 > 0 ? 'High':'Medium', action:'Open collections review'})
  if (growth >= 15 && utilization >= 75) items.push({id:'growth-limit', title:'Evaluate a credit-line increase', reason:`Sales are growing ${growth.toFixed(1)}% while utilization is elevated.`, impact:'Medium', action:'Start line evaluation'})
  if (growth <= -10) items.push({id:'sales-decline', title:'Investigate sales decline', reason:`Year-to-date sales are down ${Math.abs(growth).toFixed(1)}%.`, impact:'Medium', action:'Review sales activity'})
  if (health.score < 60) items.push({id:'full-review', title:'Perform a complete account review', reason:`The explainable health score is ${health.score} (${health.status}).`, impact:'High', action:'Create review task'})
  if (items.length === 0) items.push({id:'monitor', title:'Continue routine monitoring', reason:'No material credit, aging, or sales exceptions are currently detected.', impact:'Low', action:'No immediate action'})
  return items
}
