import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useFetch } from './api'

const FiltersContext = createContext(null)

export function FiltersProvider({ user, children }) {
  const dates = useFetch('/api/ingest/run-dates')
  const [runDate, setRunDate] = useState('')
  const [location, setLocation] = useState(user.role === 'SUPPORT' ? '' : user.location)
  const [currency, setCurrency] = useState('USD')

  useEffect(() => {
    const list = dates.data || []
    if (list.length && !list.some(d => d.run_date === runDate)) setRunDate(list[0].run_date)
  }, [dates.data])

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
