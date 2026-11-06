import { Accessibility, ArrowRight, BadgeCheck, Clock, Footprints, Luggage, MapPin, Minus, Plus, Ticket, Users } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { pxApi, useLive } from '../../lib/api'
import { parseHhmm } from '../../lib/format'
import { Button, Card, CheckRow, Field, SectionHead, useDo } from '../ui'

const NEEDS = [
  { id: 'wheelchair', label: 'Wheelchair user', icon: Accessibility },
  { id: 'step_free', label: 'Step-free access', icon: Footprints },
  { id: 'luggage', label: 'Large luggage', icon: Luggage },
]

const PARTY_PRESETS = [[1, 'Solo'], [2, 'Party of 2'], [3, 'Party of 3'], [4, 'Party of 4']] as const
const MAX_PARTY = 8

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

  const stepButton = 'flex size-11 cursor-pointer items-center justify-center rounded-xl disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <form onSubmit={submit} className="grid gap-4">
      <section className="rounded-2xl bg-px-mid p-5">
        <h1 className="text-2xl font-semibold leading-tight tracking-tight">Where do you need to be?</h1>
        <p className="mt-1 text-px-muted">We use this to find options that really work for you. Times are for today's simulated service.</p>
      </section>

      <Card>
        <div className="flex items-center justify-between gap-3">
          <SectionHead icon={Users} title="Party size" sub="How many people are travelling?" />
          <div className="flex shrink-0 items-center gap-1 rounded-xl bg-px-low p-1">
            <button type="button" aria-label="Fewer people" className={`${stepButton} text-px-ink`} disabled={f.party <= 1} onClick={() => set('party', f.party - 1)}><Minus size={18} /></button>
            <span className="num w-7 text-center font-display text-xl font-semibold" aria-live="polite">{f.party}</span>
            <button type="button" aria-label="More people" className={`${stepButton} bg-px-accent text-white`} disabled={f.party >= MAX_PARTY} onClick={() => set('party', f.party + 1)}><Plus size={18} /></button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PARTY_PRESETS.map(([n, label]) => (
            <button
              key={n} type="button" aria-pressed={f.party === n} onClick={() => set('party', n)}
              className={`min-h-11 cursor-pointer rounded-xl px-2 text-sm font-semibold ${f.party === n ? 'bg-px-highest text-px-accent' : 'bg-px-low text-px-muted hover:bg-px-mid'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-3 flex items-center gap-2 rounded-xl bg-px-low px-3 py-2 text-sm"><BadgeCheck size={17} className="shrink-0 text-px-good" /> We always keep your party together.</p>
      </Card>

      <Card>
        <SectionHead icon={MapPin} title="Your route" sub="Where you are and where you're going" />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
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
      </Card>

      <Card>
        <SectionHead icon={Clock} title="Timing" sub="When you can leave and when you must arrive" />
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Field label="Leave from"><input className="px-input" type="time" required value={f.from} onChange={(e) => set('from', e.target.value)} /></Field>
          <Field label="Leave by"><input className="px-input" type="time" required value={f.to} onChange={(e) => set('to', e.target.value)} /></Field>
          <Field label="Arrive by"><input className="px-input" type="time" required value={f.arrive} onChange={(e) => set('arrive', e.target.value)} /></Field>
        </div>
      </Card>

      <Card>
        <SectionHead icon={Accessibility} title="Mobility and accessibility" sub="Anything we should plan around?" />
        <div className="mt-4 grid gap-2">
          {NEEDS.map((n) => (
            <CheckRow
              key={n.id} icon={n.icon} label={n.label} checked={f.needs.includes(n.id)}
              onChange={(e) => set('needs', e.target.checked ? [...f.needs, n.id] : f.needs.filter((x) => x !== n.id))}
            />
          ))}
        </div>
        <div className="mt-4">
          <Field label="How far can you walk to a pickup?">
            <select className="px-input" value={f.walk} onChange={(e) => set('walk', Number(e.target.value))}>
              <option value={0}>I need to be picked up here</option>
              <option value={500}>Up to 500 m</option>
              <option value={1500}>Up to 1.5 km</option>
              <option value={2500}>Up to 2.5 km</option>
            </select>
          </Field>
        </div>
      </Card>

      <Card>
        <SectionHead icon={Ticket} title="Your booking" sub="Optional" />
        <div className="mt-4">
          <Field label="Were you booked on a service?" hint="If it's disrupted, we'll start finding alternatives straight away.">
            <select className="px-input" value={f.service} onChange={(e) => set('service', e.target.value)}>
              <option value="">No booking</option>
              {services?.map((s: any) => <option key={s.id} value={s.id}>{s.name}{s.status === 'cancelled' ? ' (cancelled)' : ''}</option>)}
            </select>
          </Field>
        </div>
      </Card>

      <Button type="submit" disabled={busy} className="min-h-14 text-lg">Register my journey <ArrowRight size={20} /></Button>
    </form>
  )
}
