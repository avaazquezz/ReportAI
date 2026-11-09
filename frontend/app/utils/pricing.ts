// The launch prices the landing shows (€ a month before VAT) and each plan's monthly reports.
// The quotas must match backend/app/services/plans.py PLANS; "solo" is not there yet and arrives
// with billing (Fase 8), which will also serve these figures from the API instead of from here.
export const PRICED_PLANS = [
  { key: 'solo', price: 29, reports: 20 },
  { key: 'starter', price: 59, reports: 50 },
  { key: 'pro', price: 149, reports: 250 },
  { key: 'business', price: 349, reports: 1000 }
] as const
