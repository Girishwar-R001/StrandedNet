import {
  Accessibility, ArrowRight, Bus, Car, Check, ChevronDown, ChevronRight, CircleCheck, Clock, Hourglass, ListOrdered,
  MapPin, Route, Scale, Timer, TriangleAlert, Users, type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { pxApi, useLive } from '../../lib/api'
import { hhmm, plural, REQUIREMENT_LABEL } from '../../lib/format'
import MatchCard from '../MatchCard'
import SurgeBanner from '../SurgeBanner'
import { Button, Card, Eyebrow, IconTile, Pill, toneBox, useDo, type Tone } from '../ui'

const STEPS = [
  { label: 'Service disrupted', detail: 'We know your journey is affected.' },
  { label: 'Your choices', detail: "Rank what suits you. Choosing isn't booking." },
  { label: 'Being arranged', detail: 'Seats are allocated by published rules, not by who taps first.' },
  { label: 'Confirmed', detail: "It's only yours once it shows as confirmed here." },
]

// Mirrors the allocation engine: accessibility is a hard constraint, the rest are scored factors.
const FAIRNESS: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: Accessibility, title: 'Accessibility comes first', body: "This is a rule, not a score. You're never placed on a vehicle that can't carry you." },
  { icon: Hourglass, title: 'Waiting time and urgency', body: "How long you've waited and how close you are to your arrival deadline." },
  { icon: Route, title: 'Lack of alternatives', body: 'Parties with no other way to arrive in time are weighted higher.' },
  { icon: Users, title: 'Parties stay together', body: 'Your whole party travels on the same vehicle.' },
  { icon: ListOrdered, title: 'Your preferences', body: 'Your ranked choices count towards the decision, but they are not a booking.' },
]

function stepFor(code: string) {
  if (code === 'choose_options') return 1
  if (code === 'preference_submitted' || code === 'no_official_seat' || code === 'carpool_listed') return 2
  if (code === 'operator_approved' || code === 'carpool_proposed') return 3
  if (code === 'seat_confirmed' || code === 'carpool_confirmed') return 4
  return 0
}

function Stepper({ done }: { done: number }) {
  return (
    <Card>
      <Eyebrow>Where things stand</Eyebrow>
      <ol className="mt-3" aria-label="Journey progress">
        {STEPS.map(({ label, detail }, i) => {
          const complete = i < done
          const active = i === done
          return (
            <li key={label} className="relative flex gap-3 pb-2 last:pb-0" aria-current={active ? 'step' : undefined}>
              {i < STEPS.length - 1 && <span className={`absolute bottom-0 left-[15px] top-8 w-0.5 ${complete ? 'bg-px-good' : 'bg-px-line'}`} />}
              <span className={`z-10 flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${complete ? 'bg-px-good text-white' : active ? 'bg-px-accent text-white' : 'bg-px-mid text-px-muted'}`}>
                {complete ? <Check size={16} /> : i + 1}
              </span>
              <div className={`min-w-0 flex-1 rounded-xl px-3 py-2 ${active ? 'bg-px-high' : complete ? 'bg-px-low' : ''}`}>
                <p className={`text-[15px] font-semibold ${!complete && !active ? 'text-px-muted' : ''}`}>{label}</p>
                {(complete || active) && <p className="text-sm text-px-muted">{detail}</p>}
              </div>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}

function Fairness() {
  return (
    <Card>
      <details>
        <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-3">
          <span className="flex items-center gap-2.5 font-display text-lg font-semibold"><Scale size={20} className="text-px-accent" /> How seats are allocated</span>
          <ChevronDown size={20} className="chevron shrink-0 text-px-muted transition-transform" />
        </summary>
        <ul className="mt-3 grid gap-2">
          {FAIRNESS.map(({ icon: Icon, title, body }) => (
            <li key={title} className="flex gap-3 rounded-xl bg-px-low p-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-px-high text-px-accent"><Icon size={16} aria-hidden="true" /></span>
              <span className="min-w-0">
                <span className="block text-[15px] font-semibold">{title}</span>
                <span className="block text-sm text-px-muted">{body}</span>
              </span>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  )
}

function Ticket({ journey, onChange }: { journey: any; onChange: () => void }) {
  const a = journey.allocation
  const { busy, run } = useDo()
  const [giving, setGiving] = useState(false)
  return (
    <Card flush>
      <div className="flex items-center justify-between gap-2 bg-px-mid px-5 py-2.5">
        <p className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase tracking-wider">
          <Bus size={16} className="shrink-0 text-px-accent" /> <span className="truncate">Official replacement</span>
        </p>
        {a.status === 'confirmed' && <Pill tone="good"><Check size={13} /> Seat reserved</Pill>}
        {a.status === 'approved' && <Pill tone="info">Approved, not yet reserved</Pill>}
        {a.status === 'needs_review' && <Pill tone="warn">Under review</Pill>}
      </div>

      <div className="p-5">
        <Eyebrow>Destination</Eyebrow>
        <h3 className="mt-0.5 text-2xl font-semibold leading-tight tracking-tight">{journey.destination}</h3>
        <p className="mt-1 text-[15px] text-px-muted">From {journey.origin}</p>

        <dl className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-px-low p-3">
            <dt><Eyebrow>Vehicle</Eyebrow></dt>
            <dd className="mt-0.5 font-display text-lg font-semibold leading-snug">{a.vehicle_id}</dd>
            <dd className="text-sm text-px-muted">{a.vehicle_type}</dd>
          </div>
          <div className="rounded-xl bg-px-high p-3">
            <dt><Eyebrow>Be at</Eyebrow></dt>
            <dd className="mt-0.5 font-display text-lg font-semibold leading-snug">{a.pickup_stop}</dd>
            <dd className="num text-sm text-px-muted">Pickup {hhmm(a.pickup_min)}</dd>
          </div>
        </dl>
        <dl className="mt-2 flex items-center justify-between gap-3 rounded-xl bg-px-low px-3 py-2.5 text-[15px]">
          <div className="flex gap-1.5"><dt className="text-px-muted">Estimated arrival</dt><dd className="num font-semibold">{hhmm(a.arrival_min)}</dd></div>
          <div className="flex gap-1.5"><dt className="text-px-muted">Seats</dt><dd className="num font-semibold">{a.seats}</dd></div>
        </dl>
      </div>

      <div className="relative" aria-hidden="true">
        <div className="mx-5 border-t-2 border-dashed border-px-line" />
        <span className="absolute -left-3 -top-3 size-6 rounded-full bg-px-bg" />
        <span className="absolute -right-3 -top-3 size-6 rounded-full bg-px-bg" />
      </div>

      <div className="p-5 text-center">
        <Eyebrow>Journey reference</Eyebrow>
        <p className="num mx-auto mt-1 w-fit rounded-xl bg-px-mid px-4 py-1.5 font-display text-2xl font-bold tracking-[0.15em] text-px-accent">{journey.ref}</p>
        {a.status === 'confirmed' && (
          <div className="mt-3">
            {giving ? (
              <div className="rounded-xl bg-px-warn-soft p-3 text-left">
                <p className="text-[15px]">Give up your seat? It goes to someone else and you may not get it back.</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button variant="danger" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/decline-seat`, { reason: 'No longer needed' }).then(onChange), 'Your seat has been released')}>Yes, release it</Button>
                  <Button variant="secondary" onClick={() => setGiving(false)}>Keep my seat</Button>
                </div>
              </div>
            ) : <Button variant="danger" className="w-full" onClick={() => setGiving(true)}>I no longer need this seat</Button>}
          </div>
        )}
      </div>
    </Card>
  )
}

function JourneyCard({ journey, matches, now, onChange }: { journey: any; matches: any[]; now?: number; onChange: () => void }) {
  const stage = journey.stage
  const { busy, run } = useDo()
  const tone = stage.tone as Tone
  const canChoose = !journey.preferences_locked && journey.status === 'affected'
  const myMatches = matches.filter((m) => m.role === 'passenger' && m.status !== 'cancelled')
  const done = stepFor(stage.code)
  const confirmed = done === 4
  const pickupIn = confirmed && journey.allocation && now !== undefined ? journey.allocation.pickup_min - now : 0

  return (
    <div className="grid gap-4">
      <section className={`rounded-2xl p-5 ${confirmed ? 'bg-px-good-strong text-white' : toneBox[tone]}`}>
        <Eyebrow className={confirmed ? 'flex items-center gap-1.5 text-white' : 'flex items-center gap-1.5'}>
          {confirmed && <CircleCheck size={15} />} Journey {journey.ref}
        </Eyebrow>
        <h1 className={`mt-1 text-2xl font-semibold leading-tight tracking-tight ${confirmed ? '' : 'text-px-ink'}`}>{stage.headline}</h1>
        <p className={`mt-1.5 text-[17px] ${confirmed ? 'text-white' : 'text-px-muted'}`}>{stage.detail}</p>
        {pickupIn > 0 && (
          <p className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-black/15 px-3 py-2">
            <span className="flex items-center gap-2 text-[15px]"><Timer size={17} /> Pickup in</span>
            <span className="num font-display text-xl font-bold">{plural(pickupIn, 'min', 'mins')}</span>
          </p>
        )}
      </section>

      {journey.disruption && journey.status !== 'normal' && (
        <p className="flex items-start gap-2.5 rounded-xl bg-px-warn-soft px-4 py-3 text-[15px] text-px-warn">
          <TriangleAlert size={18} className="mt-0.5 shrink-0" /> {journey.disruption.description}
        </p>
      )}

      {canChoose && journey.preferences.length === 0 && (
        <Link to={`/app/journey/${journey.id}/options`}>
          <Button className="w-full">Compare my options <ArrowRight size={18} /></Button>
        </Link>
      )}

      {journey.allocation && <Ticket journey={journey} onChange={onChange} />}

      {myMatches.map((m) => <MatchCard key={m.id} match={m} onChange={onChange} />)}

      {done > 0 && !confirmed && <Stepper done={done} />}

      {journey.preferences.length > 0 && journey.status === 'affected' && (
        <Card>
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-lg font-semibold">Your preferences</h3>
            <Pill tone="neutral">Not a booking</Pill>
          </div>
          <ol className="mt-3 grid gap-2">
            {journey.preferences.map((p: any) => (
              <li key={p.rank} className="flex items-start gap-3 rounded-xl bg-px-low p-3 text-[15px]">
                <span className={`flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${p.rank === 1 ? 'bg-px-accent text-white' : 'bg-px-highest text-px-accent'}`}>{p.rank}</span>
                <span className="min-w-0">
                  <span className="font-medium">{p.title}</span>
                  <span className="block text-sm text-px-muted">{p.status === 'invalidated' ? 'No longer available, please choose again' : p.availability.label}</span>
                </span>
              </li>
            ))}
          </ol>
          {canChoose && <Link to={`/app/journey/${journey.id}/options`} className="mt-3 inline-flex min-h-11 items-center text-[15px] font-semibold text-px-accent underline underline-offset-2">Change my choices</Link>}
        </Card>
      )}

      {stage.code === 'carpool_listed' && (
        <Card>
          <div className="flex items-start gap-3">
            <IconTile icon={Car} />
            <div className="min-w-0">
              <h3 className="text-lg font-semibold leading-snug">You're on a community carpool listing</h3>
              <p className="mt-1 text-[15px] text-px-muted">
                Drivers already heading your way can see your area, destination and party size, but never your name or number. Nothing happens without your say-so.
              </p>
              <Button variant="quiet" className="mt-1" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/leave-carpool`).then(onChange), "You've left the carpool listing")}>Leave the listing</Button>
            </div>
          </div>
        </Card>
      )}
      {journey.carpool_opt_out && journey.status === 'affected' && (
        <Button variant="secondary" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/join-carpool`).then(onChange), 'Back on the carpool listing')}>Rejoin the carpool listing</Button>
      )}

      {done > 1 && !confirmed && <Fairness />}

      <Card>
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-lg font-semibold">Your journey</h3>
          <span className="num rounded-md bg-px-mid px-2 py-0.5 text-sm font-medium">{journey.ref}</span>
        </div>
        <ul className="mt-2 grid gap-1.5 text-[15px]">
          <li className="flex items-center gap-2"><MapPin size={16} className="shrink-0 text-px-accent" /> {journey.origin} to {journey.destination}</li>
          <li className="flex items-center gap-2"><Clock size={16} className="shrink-0 text-px-accent" /> Leaving {hhmm(journey.dep_earliest)}–{hhmm(journey.dep_latest)}, arrive by {hhmm(journey.latest_arrival)}</li>
          <li className="flex items-center gap-2 text-px-muted"><Users size={16} className="shrink-0 text-px-accent" /> {plural(journey.party_size, 'person', 'people')}{journey.requirements.length ? ` · ${journey.requirements.map((r: string) => REQUIREMENT_LABEL[r]).join(', ')}` : ''}{journey.booked_service_id ? ` · Booked on ${journey.booked_service_id}` : ''}</li>
        </ul>
        {journey.status === 'normal' && (
          <Button variant="quiet" className="mt-2" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/report-affected`).then(onChange), 'Thanks. We have your journey')}>My journey is affected</Button>
        )}
        {journey.status === 'affected' && (
          <Button variant="quiet" className="mt-2" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/self-resolve`).then(onChange), "OK, we've stopped looking for you")}>I've made my own arrangements</Button>
        )}
      </Card>
    </div>
  )
}

function LinkRow({ to, icon, title, body }: { to: string; icon: LucideIcon; title: string; body: string }) {
  return (
    <Link to={to} className="flex items-center gap-3 rounded-2xl bg-px-card p-4 shadow-card hover:bg-px-low">
      <IconTile icon={icon} />
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">{title}</span>
        <span className="block text-sm text-px-muted">{body}</span>
      </span>
      <ChevronRight size={20} className="shrink-0 text-px-muted" />
    </Link>
  )
}

export default function Home() {
  const { data: journeys, error, refetch } = useLive(pxApi, '/me/journeys')
  const { data: matches, refetch: refetchMatches } = useLive(pxApi, '/carpool/matches/mine')
  const { data: disruptions } = useLive(pxApi, '/me/disruptions')
  const { data: me } = useLive(pxApi, '/auth/me')
  const { data: meta } = useLive(pxApi, '/meta')
  if (!journeys) return <p className="py-10 text-center text-px-muted">{error ?? 'Loading your journey…'}</p>

  const refresh = () => {
    refetch()
    refetchMatches()
  }
  const driving = (matches ?? []).filter((m: any) => m.role === 'provider' && m.status !== 'cancelled')

  return (
    <div className="grid gap-6">
      {journeys.length === 0 && (
        <section className="rounded-2xl bg-px-mid p-5">
          <h1 className="text-2xl font-semibold tracking-tight">Hello{me ? `, ${me.name.split(' ')[0]}` : ''}</h1>
          <p className="mt-1 text-px-muted">You have no journeys registered.</p>
        </section>
      )}

      {disruptions?.length > 0 && journeys.every((j: any) => j.status === 'normal') && (
        <section className="rounded-2xl bg-px-warn-soft p-5">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><TriangleAlert size={18} className="text-px-warn" /> Current disruptions</h2>
          <ul className="mt-2 grid gap-1 text-[15px]">
            {disruptions.map((d: any) => <li key={d.code}>{d.description}</li>)}
          </ul>
        </section>
      )}

      <SurgeBanner />

      {journeys.map((j: any) => <JourneyCard key={j.id} journey={j} matches={matches ?? []} now={meta?.now} onChange={refresh} />)}

      {driving.length > 0 && (
        <section className="grid gap-3">
          <h2 className="text-lg font-semibold">Rides you're offering</h2>
          {driving.map((m: any) => <MatchCard key={m.id} match={m} onChange={refresh} />)}
        </section>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <LinkRow to="/app/journey/new" icon={MapPin} title="Register a journey" body="Tell us where you need to be." />
        <LinkRow to="/app/carpool" icon={Car} title="Offer a spare seat" body="Already heading that way? Help someone out." />
      </div>
    </div>
  )
}
