import { useCallback, useEffect, useRef, useState } from 'react'

export type Role = 'operator' | 'passenger'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function readDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '')
  return fallback
}

/**
 * One client per dashboard. Tokens live in sessionStorage under a per-role key, so an operator
 * tab and passenger tabs signed in as different people can run side by side during a demo.
 */
export class Client {
  role: Role
  private listeners = new Set<() => void>()
  private socket: WebSocket | null = null
  private retry: number | undefined
  private beat: number | undefined

  constructor(role: Role) {
    this.role = role
  }

  private get key() {
    return `sn_token_${this.role}`
  }
  get token() {
    return sessionStorage.getItem(this.key)
  }
  setToken(token: string | null) {
    if (token) sessionStorage.setItem(this.key, token)
    else sessionStorage.removeItem(this.key)
    this.socket?.close()
  }

  async request<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const res = await fetch(`/api${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    const text = await res.text()
    let data: unknown = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      /* non-JSON error page */
    }
    if (!res.ok) throw new ApiError(res.status, readDetail(data, `Request failed (${res.status})`))
    return data as T
  }

  get<T = any>(path: string) {
    return this.request<T>(path)
  }
  post<T = any>(path: string, body: unknown = {}) {
    return this.request<T>(path, 'POST', body)
  }
  put<T = any>(path: string, body: unknown) {
    return this.request<T>(path, 'PUT', body)
  }
  patch<T = any>(path: string, body: unknown) {
    return this.request<T>(path, 'PATCH', body)
  }

  /** The socket carries only a "something changed" ping. Data always comes via the REST API. */
  subscribe(fn: () => void) {
    this.listeners.add(fn)
    this.connect()
    return () => {
      this.listeners.delete(fn)
    }
  }

  private connect() {
    if (this.socket || !this.token) return
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${scheme}://${location.host}/api/ws?token=${this.token}`)
    this.socket = ws
    ws.onopen = () => {
      this.beat = window.setInterval(() => ws.readyState === 1 && ws.send('ping'), 30000)
    }
    ws.onmessage = () => this.listeners.forEach((l) => l())
    ws.onclose = () => {
      clearInterval(this.beat)
      this.socket = null
      clearTimeout(this.retry)
      if (this.listeners.size) this.retry = window.setTimeout(() => this.connect(), 2000)
    }
  }
}

export const opApi = new Client('operator')
export const pxApi = new Client('passenger')

/** Fetches a resource and keeps it current: socket ping first, slow poll as a safety net. */
export function useLive<T = any>(client: Client, path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const latest = useRef(path)
  latest.current = path

  const refetch = useCallback(async () => {
    if (!path) return
    try {
      const result = await client.get<T>(path)
      if (latest.current === path) {
        setData(result)
        setError(null)
      }
    } catch (e) {
      if (latest.current === path) setError((e as Error).message)
    } finally {
      if (latest.current === path) setLoading(false)
    }
  }, [client, path])

  useEffect(() => {
    refetch()
    const off = client.subscribe(refetch)
    const poll = window.setInterval(refetch, 15000)
    return () => {
      off()
      clearInterval(poll)
    }
  }, [client, refetch])

  return { data, error, loading, refetch }
}
