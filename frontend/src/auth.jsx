import { createContext, useContext, useEffect, useState } from 'react'
import { api, setToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!sessionStorage.getItem('token')) return setReady(true)
    api.get('/api/auth/me').then(setUser, () => setToken(null)).finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const expire = () => setUser(null)
    window.addEventListener('session-expired', expire)
    return () => window.removeEventListener('session-expired', expire)
  }, [])

  async function login(username, password) {
    const res = await api.post('/api/auth/login', { username, password })
    setToken(res.access_token)
    setUser(res.user)
  }

  function logout() {
    setToken(null)
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, ready, login, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
