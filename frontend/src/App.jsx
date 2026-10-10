import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { FiltersProvider } from './filters'
import Layout from './components/Layout'
import Login from './pages/Login'
import Ladder from './pages/Ladder'
import Compare from './pages/Compare'
import WhatIf from './pages/WhatIf'
import Recommendations from './pages/Recommendations'
import Analytics from './pages/Analytics'
import Data from './pages/Data'

export default function App() {
  const { user, ready } = useAuth()
  if (!ready) return null
  if (!user) return <Login />

  return (
    <FiltersProvider user={user}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/ladder" element={<Ladder key="d" view="deterministic" />} />
          <Route path="/ai" element={<Ladder key="a" view="ai" />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/what-if" element={<WhatIf />} />
          <Route path="/actions" element={<Recommendations />} />
          <Route path="/history" element={<Analytics />} />
          {user.role === 'SUPPORT' && <Route path="/data" element={<Data />} />}
          <Route path="*" element={<Navigate to="/ladder" replace />} />
        </Route>
      </Routes>
    </FiltersProvider>
  )
}
