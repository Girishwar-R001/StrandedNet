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

const POLL_MS = 15000
// Operators are few and need the KPIs to move at once. Passengers are many and can wait a moment.
const PING_SPREAD_MS: Record<Role, number> = { operator: 250, passenger: 3000 }

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
  private poll: number | undefined
  private pending: number | undefined
  private inFlight = new Map<string, Promise<unknown>>()

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

  /** Identical reads running at the same moment share one request. */
  get<T = any>(path: string): Promise<T> {
    const running = this.inFlight.get(path)
    if (running) return running as Promise<T>
    const request = this.request<T>(path).finally(() => this.inFlight.delete(path))
    this.inFlight.set(path, request)
    return request
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
    // One timer per tab, so every hook refreshes together and duplicate reads can be shared.
    this.poll ??= window.setInterval(() => this.refresh(), POLL_MS)
    return () => {
      this.listeners.delete(fn)
      if (!this.listeners.size) {
        clearInterval(this.poll)
        this.poll = undefined
      }
    }
  }

  private refresh() {
    this.listeners.forEach((l) => l())
  }

  /** A write pings every tab at once. A random delay spreads the reload across the crowd, and
   *  any further pings during the wait fold into the same single refresh. */
  private schedule() {
    if (this.pending !== undefined) return
    this.pending = window.setTimeout(() => {
      this.pending = undefined
      this.refresh()
    }, Math.random() * PING_SPREAD_MS[this.role])
  }

  private connect() {
    if (this.socket || !this.token) return
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${scheme}://${location.host}/api/ws?token=${this.token}`)
    this.socket = ws
    ws.onopen = () => {
      this.beat = window.setInterval(() => ws.readyState === 1 && ws.send('ping'), 30000)
    }
    ws.onmessage = () => this.schedule()
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

/** Fetches a resource and keeps it current: socket ping first, slow shared poll as a safety net. */
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
    return client.subscribe(refetch)
  }, [client, refetch])

  return { data, error, loading, refetch }
}
