import { useState } from 'react'
import { useAuth } from '../auth'

export default function Login() {
  const { login } = useAuth()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    const { username, password } = e.target.elements
    setBusy(true)
    setError('')
    try {
      await login(username.value.trim(), password.value)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="login-side">
        <span className="brand">Liquid<b>+</b></span>
        <p>Liquidity gap forecasting for IBC treasury. Contractual and behavioral maturity ladders, by currency and location.</p>
      </div>
      <form onSubmit={submit}>
        <h1>Sign in</h1>
        <label>Username<input name="username" autoComplete="username" required /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
