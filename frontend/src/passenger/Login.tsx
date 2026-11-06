import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Logo from '../Logo'
import { pxApi } from '../lib/api'
import { Button, Card, Field } from './ui'

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '' })
  const [error, setError] = useState('')
  const [demo, setDemo] = useState<any>(null)
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  useEffect(() => {
    pxApi.get('/demo/accounts').then(setDemo).catch(() => setDemo(null))
  }, [])

  const enter = async (fn: () => Promise<any>) => {
    setError('')
    try {
      const res = await fn()
      if (res.user.role !== 'passenger') {
        setError('Operator accounts use the operator console.')
        return
      }
      pxApi.setToken(res.token)
      navigate('/app')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const accounts = demo?.accounts.filter((a: any) => a.role === 'passenger') ?? []
  const drivers = accounts.filter((a: any) => !a.ref)
  const travellers = accounts.filter((a: any) => a.ref)

  return (
    <div className="px-root min-h-full">
      <div className="mx-auto max-w-md px-4 py-10">
        <Link to="/" className="inline-flex items-center gap-2.5 font-display text-[17px] font-semibold"><Logo /> The Stranded Network</Link>
        <h1 className="mt-8 text-3xl font-bold tracking-tight">{mode === 'in' ? 'Welcome back' : 'Create your account'}</h1>
        <p className="mt-1 text-px-muted">See your journey, your options and your ride.</p>

        <Card className="mt-6">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            enter(() => mode === 'in'
              ? pxApi.post('/auth/login', { email: form.email, password: form.password })
              : pxApi.post('/auth/register', form))
          }}
        >
          {mode === 'up' && <Field label="Your name"><input className="px-input" required minLength={2} value={form.name} onChange={(e) => set('name', e.target.value)} /></Field>}
          <Field label="Email"><input className="px-input" type="email" autoComplete="username" required value={form.email} onChange={(e) => set('email', e.target.value)} /></Field>
          {mode === 'up' && <Field label="Phone" hint="Only shared with a driver or passenger after you both confirm a ride."><input className="px-input" type="tel" value={form.phone} onChange={(e) => set('phone', e.target.value)} /></Field>}
          <Field label="Password"><input className="px-input" type="password" autoComplete={mode === 'in' ? 'current-password' : 'new-password'} required minLength={mode === 'up' ? 8 : undefined} value={form.password} onChange={(e) => set('password', e.target.value)} /></Field>
          {error && <p className="text-[15px] text-px-bad" role="alert">{error}</p>}
          <Button type="submit">{mode === 'in' ? 'Sign in' : 'Create account'}</Button>
        </form>
        <p className="mt-2 text-center">
          <Button variant="quiet" onClick={() => { setMode(mode === 'in' ? 'up' : 'in'); setError('') }}>
            {mode === 'in' ? 'New here? Create an account' : 'Already registered? Sign in'}
          </Button>
        </p>
        </Card>

        {demo && (
          <div className="mt-8">
            <h2 className="text-lg font-semibold">Demo accounts</h2>
            <p className="text-sm text-px-muted">Each browser tab can hold a different person, so you can open several side by side.</p>
            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider text-px-muted">Community drivers (no affected journey)</h3>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {drivers.map((a: any) => (
                <button key={a.email} className="cursor-pointer min-h-11 rounded-xl bg-px-mid px-3 py-1.5 text-sm font-medium hover:bg-px-high"
                  onClick={() => enter(() => pxApi.post('/auth/login', { email: a.email, password: demo.password }))}>
                  {a.name}
                </button>
              ))}
            </div>
            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider text-px-muted">Passengers</h3>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {travellers.map((a: any) => (
                <button key={a.email} className="cursor-pointer min-h-11 rounded-xl bg-px-mid px-3 py-1.5 text-sm font-medium hover:bg-px-high"
                  onClick={() => enter(() => pxApi.post('/auth/login', { email: a.email, password: demo.password }))}>
                  {a.name.split(' ')[0]} <span className="font-normal text-px-muted">{a.ref}, party of {a.party_size}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
