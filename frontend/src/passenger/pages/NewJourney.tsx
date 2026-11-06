import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { pxApi, useLive } from '../../lib/api'
import { parseHhmm } from '../../lib/format'
import { Button, Field, useDo } from '../ui'

const NEEDS = [
  { id: 'wheelchair', label: 'Wheelchair user' },
  { id: 'step_free', label: 'Step-free access' },
  { id: 'luggage', label: 'Large luggage' },
]

export default function NewJourney() {
  const navigate = useNavigate()
  const { data: stops } = useLive(pxApi, '/network/stops')
  const { data: services } = useLive(pxApi, '/network/services')
  const { busy, run } = useDo()
  const [f, setF] = useState({ origin: '', dest: '', party: 1, from: '18:00', to: '18:30', arrive: '19:30', walk: 500, service: '', needs: [] as string[] })
  const set = (k: string, v: unknown) => setF((s) => ({ ...s, [k]: v }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const ok = await run(() => pxApi.post('/me/journeys', {
      origin_stop: f.origin, dest_stop: f.dest, party_size: f.party, dep_earliest: parseHhmm(f.from),
      dep_latest: parseHhmm(f.to), latest_arrival: parseHhmm(f.arrive), max_walk_m: f.walk,
      requirements: f.needs, booked_service_id: f.service || null,
    }), 'Journey registered')
    if (ok) navigate('/app')
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Where do you need to be?</h1>
        <p className="mt-1 text-px-muted">We use this to find options that really work for you. Times are for today's simulated service.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="I'm near">
          <select className="px-input" required value={f.origin} onChange={(e) => set('origin', e.target.value)}>
            <option value="">Choose a stop</option>
            {stops?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Going to">
          <select className="px-input" required value={f.dest} onChange={(e) => set('dest', e.target.value)}>
            <option value="">Choose a stop</option>
            {stops?.filter((s: any) => s.id !== f.origin).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
      </div>

      <Field label="How many people are travelling?" hint="We always keep your party together.">
        <input className="px-input" type="number" min={1} max={8} required value={f.party} onChange={(e) => set('party', Number(e.target.value))} />
      </Field>

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Leave from"><input className="px-input" type="time" required value={f.from} onChange={(e) => set('from', e.target.value)} /></Field>
        <Field label="Leave by"><input className="px-input" type="time" required value={f.to} onChange={(e) => set('to', e.target.value)} /></Field>
        <Field label="Arrive by"><input className="px-input" type="time" required value={f.arrive} onChange={(e) => set('arrive', e.target.value)} /></Field>
      </div>

      <fieldset>
        <legend className="text-[15px] font-medium">Anything we should plan around?</legend>
        <div className="mt-1 grid gap-1">
          {NEEDS.map((n) => (
            <label key={n.id} className="flex items-center gap-2.5 py-1">
              <input
                type="checkbox" className="size-4 accent-[#0f6b5c]" checked={f.needs.includes(n.id)}
                onChange={(e) => set('needs', e.target.checked ? [...f.needs, n.id] : f.needs.filter((x) => x !== n.id))}
              />
              {n.label}
            </label>
          ))}
        </div>
      </fieldset>

      <Field label="How far can you walk to a pickup?">
        <select className="px-input" value={f.walk} onChange={(e) => set('walk', Number(e.target.value))}>
          <option value={0}>I need to be picked up here</option>
          <option value={500}>Up to 500 m</option>
          <option value={1500}>Up to 1.5 km</option>
          <option value={2500}>Up to 2.5 km</option>
        </select>
      </Field>

      <Field label="Were you booked on a service?" hint="Optional. If it's disrupted, we'll start finding alternatives straight away.">
        <select className="px-input" value={f.service} onChange={(e) => set('service', e.target.value)}>
          <option value="">No booking</option>
          {services?.map((s: any) => <option key={s.id} value={s.id}>{s.name}{s.status === 'cancelled' ? ' (cancelled)' : ''}</option>)}
        </select>
      </Field>

      <Button type="submit" disabled={busy}>Register my journey</Button>
    </form>
  )
}
