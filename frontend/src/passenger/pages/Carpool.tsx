import { ArrowRight, Car, Clock, Handshake, Luggage, MapPin, ShieldAlert, Accessibility, Users } from 'lucide-react'
import { useRef, useState } from 'react'
import { pxApi, useLive } from '../../lib/api'
import { hhmm, parseHhmm, REQUIREMENT_LABEL } from '../../lib/format'
import MatchCard from '../MatchCard'
import SurgeBanner from '../SurgeBanner'
import { Button, Card, CheckRow, Eyebrow, Field, IconTile, Pill, SectionHead, useDo } from '../ui'

const EMPTY = { origin: '', dest: '', time: '18:10', seats: 3, vehicle: 'Hatchback', wheelchair: false, luggage: true, zone: '', notes: '', consent: false }

const LISTING_STATUS: Record<string, string> = {
  open: 'Seeking a driver',
  offer_received: 'Offer received',
  match_proposed: 'Match proposed',
  awaiting_passenger: 'Awaiting passengers',
  awaiting_provider: 'Awaiting driver',
  confirmed: 'Confirmed',
}

export default function Carpool() {
  const { data: listings, refetch } = useLive(pxApi, '/carpool/requests')
  const { data: stops } = useLive(pxApi, '/network/stops')
  const { data: offers, refetch: refetchOffers } = useLive(pxApi, '/carpool/offers/mine')
  const { data: matches, refetch: refetchMatches } = useLive(pxApi, '/carpool/matches/mine')
  const { busy, run } = useDo()
  const [f, setF] = useState(EMPTY)
  const [notes, setNotes] = useState<any[] | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const set = (k: string, v: unknown) => setF((s) => ({ ...s, [k]: v }))
  const zones: string[] = [...new Set<string>((stops ?? []).map((s: any) => s.zone))].sort()

  const refresh = () => {
    refetch()
    refetchOffers()
    refetchMatches()
  }

  const help = (r: any) => {
    setF((s) => ({ ...s, origin: r.origin_stop, dest: r.dest_stop, zone: r.origin_zone, time: hhmm(r.window_start + 10) }))
    setNotes(null)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    await run(async () => {
      const res = await pxApi.post('/carpool/offers', {
        origin_stop: f.origin, dest_stop: f.dest, departure: parseHhmm(f.time), available_seats: f.seats,
        vehicle_type: f.vehicle, wheelchair: f.wheelchair, luggage: f.luggage, pickup_zone: f.zone,
        notes: f.notes, consent: f.consent,
      })
      setNotes(res.notes)
      setF({ ...EMPTY })
      refresh()
    }, 'Thanks for offering. See what we found below.')
  }

  const live = (matches ?? []).filter((m: any) => m.status !== 'cancelled')

  return (
    <div className="grid gap-6">
      <section className="flex items-start gap-3 rounded-2xl bg-px-high p-5">
        <IconTile icon={Handshake} className="size-12 rounded-full bg-white" />
        <div className="min-w-0">
          <Eyebrow className="text-px-accent">Community safety net</Eyebrow>
          <h1 className="mt-0.5 text-2xl font-semibold leading-tight tracking-tight">Community carpool</h1>
          <p className="mt-1 text-px-muted">When official seats run out, people already heading the same way can help.</p>
        </div>
      </section>

      <p className="flex items-start gap-2.5 rounded-xl bg-px-warn-soft px-4 py-3 text-[15px] text-px-warn">
        <ShieldAlert size={18} className="mt-0.5 shrink-0" />
        <span>Community rides are offered by other users. They're separate from official transport, and drivers and vehicles aren't verified by this service. Agree only to rides you're comfortable with.</span>
      </p>

      <SurgeBanner offerLink={false} />

      {live.length > 0 && (
        <section className="grid gap-3">
          <h2 className="text-lg font-semibold">Your rides</h2>
          {live.map((m: any) => <MatchCard key={m.id} match={m} onChange={refresh} />)}
        </section>
      )}

      <section className="grid gap-3">
        <h2 className="text-lg font-semibold">People needing a ride</h2>
        {listings?.length === 0 && <Card><p className="text-px-muted">Nobody's waiting for a carpool right now.</p></Card>}
        {listings?.map((r: any) => (
          <Card key={r.id}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="text-lg font-semibold leading-snug">To {r.destination}</h3>
              <Pill tone={r.status === 'open' ? 'warn' : 'info'}>{LISTING_STATUS[r.status] ?? r.status}</Pill>
            </div>
            <ul className="mt-3 grid gap-1.5 rounded-xl bg-px-low p-3 text-[15px]">
              <li className="flex items-center gap-2"><Users size={16} className="text-px-accent" /> {r.passengers_waiting === 1 ? '1 person' : `About ${r.passengers_waiting} people`} waiting</li>
              <li className="flex items-center gap-2"><MapPin size={16} className="text-px-accent" /> Pickup: {r.pickup_area}</li>
              <li className="flex items-center gap-2"><Clock size={16} className="text-px-accent" /> Leaving {hhmm(r.window_start)}–{hhmm(r.window_end)}</li>
            </ul>
            {r.requirements.length > 0 && <p className="mt-2 text-[15px] text-px-muted">Needs: {r.requirements.map((q: string) => REQUIREMENT_LABEL[q].toLowerCase()).join(', ')}</p>}
            <Button variant="secondary" className="mt-3 w-full" onClick={() => help(r)}>I'm heading this way <ArrowRight size={18} /></Button>
          </Card>
        ))}
      </section>

      <form ref={formRef} onSubmit={submit} className="grid scroll-mt-28 gap-4 rounded-2xl bg-px-card p-5 shadow-card">
        <SectionHead icon={Car} title="Offer a ride" sub="Already making this trip? Share your spare seats." />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Starting from">
            <select className="px-input" required value={f.origin} onChange={(e) => set('origin', e.target.value)}>
              <option value="">Choose</option>
              {stops?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Going to">
            <select className="px-input" required value={f.dest} onChange={(e) => set('dest', e.target.value)}>
              <option value="">Choose</option>
              {stops?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Leaving at"><input className="px-input" type="time" required value={f.time} onChange={(e) => set('time', e.target.value)} /></Field>
          <Field label="Spare seats"><input className="px-input" type="number" min={1} max={7} required value={f.seats} onChange={(e) => set('seats', Number(e.target.value))} /></Field>
          <Field label="Vehicle"><input className="px-input" required value={f.vehicle} onChange={(e) => set('vehicle', e.target.value)} /></Field>
          <Field label="Pickup area">
            <select className="px-input" value={f.zone} onChange={(e) => set('zone', e.target.value)}>
              <option value="">Anywhere on my way</option>
              {zones.map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </Field>
        </div>
        <div className="grid gap-2">
          <CheckRow icon={Luggage} label="Room for luggage" checked={f.luggage} onChange={(e) => set('luggage', e.target.checked)} />
          <CheckRow icon={Accessibility} label="Suitable for a wheelchair" checked={f.wheelchair} onChange={(e) => set('wheelchair', e.target.checked)} />
        </div>
        <Field label="Route notes (optional)"><input className="px-input" maxLength={300} value={f.notes} onChange={(e) => set('notes', e.target.value)} /></Field>
        <label className="flex cursor-pointer items-start gap-3 rounded-xl bg-px-low p-3 text-[15px]">
          <input type="checkbox" required className="mt-0.5 size-5 shrink-0" checked={f.consent} onChange={(e) => set('consent', e.target.checked)} />
          <span>I'm already making this trip and I'm offering these seats myself. I understand this isn't official transport, and that nothing is agreed until the passengers and I both confirm.</span>
        </label>
        <Button type="submit" disabled={busy}>Offer my seats</Button>
      </form>

      {notes && (
        <Card>
          <h3 className="font-semibold">What we found</h3>
          {notes.length === 0 && <p className="mt-1 text-[15px] text-px-muted">Nobody needs a ride right now. Your offer stays open, and we'll match it if that changes.</p>}
          <ul className="mt-2 grid gap-2 text-[15px]">
            {notes.map((n) => (
              <li key={n.request}>
                <span className="font-medium">{n.request}: {n.matched ? 'match proposed' : 'not a fit'}</span>
                <span className="block text-px-muted">{n.reasons.join('. ')}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {offers?.length > 0 && (
        <section className="grid gap-3">
          <h2 className="text-lg font-semibold">Your offers</h2>
          {offers.map((o: any) => (
            <Card key={o.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-semibold">{o.origin} to {o.destination}</p>
                <Pill tone={o.status === 'open' ? 'good' : 'neutral'}>{o.status === 'open' ? 'Open' : o.status === 'withdrawn' ? 'Withdrawn' : 'Completed'}</Pill>
              </div>
              <p className="text-[15px] text-px-muted">Leaving {hhmm(o.departure)} · {o.reserved_seats} of {o.available_seats} seats matched · {o.vehicle_type}</p>
              {o.status === 'open' && (
                <Button variant="quiet" className="mt-1" disabled={busy} onClick={() => run(() => pxApi.post(`/carpool/offers/${o.id}/withdraw`).then(refresh), 'Offer withdrawn')}>Withdraw this offer</Button>
              )}
            </Card>
          ))}
        </section>
      )}
    </div>
  )
}
