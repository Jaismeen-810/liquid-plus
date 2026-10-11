import { createContext, useContext, useMemo, useState } from 'react'
import { useFetch } from './api'

const FiltersContext = createContext(null)

// local calendar date as YYYY-MM-DD (toISOString would give the UTC date)
export function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function FiltersProvider({ user, children }) {
  const dates = useFetch('/api/ingest/run-dates') // uploads: only used to know whether any data exists
  const [runDate, setRunDate] = useState(today)   // calculation date picked in the calendar
  const [location, setLocation] = useState(user.role === 'SUPPORT' ? '' : user.location)
  const [currency, setCurrency] = useState('USD')

  const params = useMemo(() => ({ run_date: runDate, location: location || undefined }), [runDate, location])

  const value = {
    runDates: dates.data || [],
    reloadDates: dates.reload,
    datesLoading: dates.loading,
    runDate, setRunDate, location, setLocation, currency, setCurrency, params,
    isSupport: user.role === 'SUPPORT',
  }
  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>
}

export const useFilters = () => useContext(FiltersContext)
