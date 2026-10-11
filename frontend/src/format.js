export const BUCKETS = ['0-1M', '1-3M', '3-12M', '1-5Y', '>5Y']
export const LOCATIONS = ['Hong Kong', 'London', 'New York', 'Paris', 'Singapore']
export const CURRENCIES = ['USD', 'EUR', 'GBP', 'SGD', 'HKD']

export const COLORS = {
  asset: '#3D8B6E',
  liability: '#B5533C',
  gap: '#1F3A5F',
  deterministic: '#A3ADBA',
  ai: '#1F3A5F',
  flag: '#B5533C',
}

export function money(value) {
  if (value === null || value === undefined) return '–'
  const abs = Math.abs(value)
  const sign = value < 0 ? '−' : ''
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}K`
  return `${sign}${abs.toFixed(0)}`
}

export const amount = value => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
export const pct = value => (value === null || value === undefined ? '–' : `${(value * 100).toFixed(1)}%`)
export const gapClass = value => (value < 0 ? 'neg' : value > 0 ? 'pos' : '')

export const CURRENCY_SYMBOLS = {
  EUR: '€',
  USD: '$',
  GBP: '£',
  SGD: 'S$',
  HKD: 'HK$',
}

export function formatCurrency(value, currency = 'EUR') {
  if (value === null || value === undefined) return '–'
  const sym = CURRENCY_SYMBOLS[currency] || (currency ? `${currency} ` : '')
  const abs = Math.abs(value)
  const sign = value < 0 ? '−' : ''
  if (abs >= 1e9) return `${sign}${sym}${(abs / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `${sign}${sym}${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${sign}${sym}${(abs / 1e3).toFixed(0)}K`
  return `${sign}${sym}${abs.toFixed(0)}`
}
