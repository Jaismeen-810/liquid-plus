import { useEffect, useState } from 'react'

const BASE = import.meta.env.VITE_API_URL || ''
let token = sessionStorage.getItem('token')

export function setToken(value) {
  token = value
  value ? sessionStorage.setItem('token', value) : sessionStorage.removeItem('token')
}

export class ApiError extends Error {
  constructor(status, message, details) {
    super(message)
    this.status = status
    this.details = details
  }
}

export function buildUrl(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin)
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
  return url
}

async function request(path, { method = 'GET', body, params } = {}) {
  const isForm = body instanceof FormData
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  if (body && !isForm) headers['Content-Type'] = 'application/json'
  const res = await fetch(buildUrl(path, params), { method, headers, body: isForm ? body : body && JSON.stringify(body) })
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('session-expired'))
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new ApiError(res.status, err.error?.message || err.message || `Request failed (${res.status})`, err.error?.details)
  }
  return res
}

export const api = {
  get: (path, params) => request(path, { params }).then(r => r.json()),
  post: (path, body, params) => request(path, { method: 'POST', body, params }).then(r => r.json()),
  async download(path, params) {
    const res = await request(path, { params })
    const name = /filename="(.+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'export'
    const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(await res.blob()), download: name })
    link.click()
    URL.revokeObjectURL(link.href)
  },
}

export function useFetch(path, params) {
  const key = JSON.stringify([path, params])
  const [state, setState] = useState({ loading: Boolean(path) })
  const [version, setVersion] = useState(0)

  useEffect(() => {
    if (!path) return setState({ loading: false })
    let live = true
    setState(s => ({ ...s, loading: true, error: null }))
    api.get(path, params).then(
      data => live && setState({ data, loading: false }),
      error => live && setState({ error, loading: false })
    )
    return () => { live = false }
  }, [key, version])

  return { ...state, reload: () => setVersion(v => v + 1) }
}
