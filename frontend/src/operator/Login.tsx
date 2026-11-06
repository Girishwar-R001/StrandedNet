import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { opApi, useLive } from '../lib/api'
import { Btn } from './ui'

export default function Login() {
  const navigate = useNavigate()
  const { data: meta } = useLive(opApi, '/meta')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const submit = async (e?: React.FormEvent, creds?: { email: string; password: string }) => {
    e?.preventDefault()
    setError('')
    try {
      const res = await opApi.post('/auth/login', creds ?? { email, password })
      if (res.user.role !== 'operator') {
        setError('This console is for operator accounts. Passengers can use the passenger app.')
        return
      }
      opApi.setToken(res.token)
      navigate('/operator')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="op-root flex min-h-full items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-xs">
        <h1 className="text-base font-medium">Operator console</h1>
        <p className="mt-1 text-xs text-op-muted">Authorised transport staff only.</p>
        <label className="mt-5 block text-xs text-op-muted">
          Email
          <input className="op-input mt-1 w-full" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="mt-3 block text-xs text-op-muted">
          Password
          <input className="op-input mt-1 w-full" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="mt-3 text-xs text-op-bad" role="alert">{error}</p>}
        <Btn type="submit" variant="primary" className="mt-4 w-full py-1.5">Sign in</Btn>
        {meta?.demo_mode && (
          <Btn className="mt-2 w-full py-1.5" onClick={() => submit(undefined, { email: 'operator@stranded.demo', password: 'demo1234' })}>
            Use demo operator
          </Btn>
        )}
        <Link to="/" className="mt-5 block text-center text-xs text-op-muted hover:text-op-text">Back</Link>
      </form>
    </div>
  )
}
