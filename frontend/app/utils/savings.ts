// The model behind the landing's "impact" calculator. Pure, so it can be checked on its own
// (tests/savings.test.ts). Every default is an assumption of the model, and the page says so.

export interface SavingsInput {
  technicians: number
  reportsPerWeek: number
  minutesBefore: number
  minutesAfter: number
  hourlyCost: number
  aiCostPerReport: number
  serverPerMonth: number
  weeksPerYear: number
}

export const SAVINGS_DEFAULTS: SavingsInput = {
  technicians: 3,
  reportsPerWeek: 6,
  minutesBefore: 35,
  minutesAfter: 8,
  hourlyCost: 28,
  // The demo on the page cost under 3 cents of AI; a longer visit costs more.
  aiCostPerReport: 0.03,
  // A small VPS, if the company has no server of its own.
  serverPerMonth: 9,
  weeksPerYear: 46
}

/** [min, max, step] of each input, for the sliders. */
export const SAVINGS_LIMITS: Record<keyof SavingsInput, readonly [number, number, number]> = {
  technicians: [1, 60, 1],
  reportsPerWeek: [1, 30, 1],
  minutesBefore: [5, 120, 5],
  minutesAfter: [1, 30, 1],
  hourlyCost: [10, 120, 1],
  aiCostPerReport: [0, 1, 0.01],
  serverPerMonth: [0, 100, 1],
  weeksPerYear: [20, 52, 1]
}

// A number field that is mid-edit reads as NaN: count it as zero rather than poison the result.
const num = (v: number) => (Number.isFinite(v) && v > 0 ? v : 0)

export function computeSavings(i: SavingsInput) {
  const reportsMonth = (num(i.technicians) * num(i.reportsPerWeek) * num(i.weeksPerYear)) / 12
  const hoursBeforeMonth = (reportsMonth * num(i.minutesBefore)) / 60
  // The new way never counts as slower than the old one: a negative saving would just be a typo.
  const hoursAfterMonth = Math.min((reportsMonth * num(i.minutesAfter)) / 60, hoursBeforeMonth)
  const hoursSavedMonth = hoursBeforeMonth - hoursAfterMonth
  const grossMonth = hoursSavedMonth * num(i.hourlyCost)
  const runningMonth = reportsMonth * num(i.aiCostPerReport) + num(i.serverPerMonth)
  const netMonth = grossMonth - runningMonth
  return {
    reportsMonth,
    hoursBeforeMonth,
    hoursAfterMonth,
    hoursSavedMonth,
    workdaysSavedMonth: hoursSavedMonth / 8,
    grossMonth,
    runningMonth,
    netMonth,
    netYear: netMonth * 12,
    /** How long the new way takes, as a share of the old one (0..1), for the bars. */
    afterShare: hoursBeforeMonth > 0 ? hoursAfterMonth / hoursBeforeMonth : 0
  }
}
