import { ArrowRight, Bus, Car, Check, Clock, MapPin, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { pxApi, useLive } from '../../lib/api'
import { hhmm, plural, REQUIREMENT_LABEL } from '../../lib/format'
import MatchCard from '../MatchCard'
import { Button, Card, Pill, toneBox, useDo, type Tone } from '../ui'

const STEPS = ['Service disrupted', 'Your choices', 'Being arranged', 'Confirmed']

function stepFor(code: string) {
  if (code === 'choose_options') return 1
  if (code === 'preference_submitted' || code === 'no_official_seat' || code === 'carpool_listed') return 2
  if (code === 'operator_approved' || code === 'carpool_proposed') return 3
  if (code === 'seat_confirmed' || code === 'carpool_confirmed') return 4
  return 0
}

function Progress({ code }: { code: string }) {
  const at = stepFor(code)
  if (!at) return null
  return (
    <ol className="mt-5 grid grid-cols-4 gap-1.5" aria-label="Journey progress">
      {STEPS.map((label, i) => {
        const done = i < at
        return (
          <li key={label}>
            <div className={`h-1 rounded-full ${done ? 'bg-current' : 'bg-black/10'}`} />
            <p className={`mt-1 text-xs leading-tight ${i === at - 1 ? 'font-medium' : 'opacity-70'}`}>{label}</p>
          </li>
        )
      })}
    </ol>
  )
}

function Ticket({ journey, onChange }: { journey: any; onChange: () => void }) {
  const a = journey.allocation
  const { busy, run } = useDo()
  const [giving, setGiving] = useState(false)
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm text-px-muted">Official replacement transport</p>
          <h3 className="flex items-center gap-2 text-xl font-semibold"><Bus size={20} className="text-px-accent" /> {a.vehicle_id}</h3>
          <p className="text-[15px] text-px-muted">{a.vehicle_type}</p>
        </div>
        {a.status === 'confirmed' && <Pill tone="good"><Check size={13} /> Seat reserved</Pill>}
        {a.status === 'approved' && <Pill tone="info">Approved, not yet reserved</Pill>}
        {a.status === 'needs_review' && <Pill tone="warn">Under review</Pill>}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-dashed border-px-line pt-4">
        <div><dt className="text-sm text-px-muted">Be at</dt><dd className="text-lg font-semibold leading-snug">{a.pickup_stop}</dd></div>
        <div><dt className="text-sm text-px-muted">Pickup time</dt><dd className="text-lg font-semibold">{hhmm(a.pickup_min)}</dd></div>
        <div><dt className="text-sm text-px-muted">Estimated arrival</dt><dd className="font-medium">{hhmm(a.arrival_min)}</dd></div>
        <div><dt className="text-sm text-px-muted">Seats</dt><dd className="font-medium">{a.seats}</dd></div>
      </dl>
      {a.status === 'confirmed' && (
        <div className="mt-4">
          {giving ? (
            <div className="rounded-lg bg-px-warn-soft p-3">
              <p className="text-[15px]">Give up your seat? It goes to someone else and you may not get it back.</p>
              <div className="mt-2 flex gap-2">
                <Button variant="danger" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/decline-seat`, { reason: 'No longer needed' }).then(onChange), 'Your seat has been released')}>Yes, release it</Button>
                <Button variant="secondary" onClick={() => setGiving(false)}>Keep my seat</Button>
              </div>
            </div>
          ) : <Button variant="quiet" onClick={() => setGiving(true)}>I no longer need this seat</Button>}
        </div>
      )}
    </Card>
  )
}

function JourneyCard({ journey, matches, onChange }: { journey: any; matches: any[]; onChange: () => void }) {
  const stage = journey.stage
  const { busy, run } = useDo()
  const tone = stage.tone as Tone
  const canChoose = !journey.preferences_locked && journey.status === 'affected'
  const myMatches = matches.filter((m) => m.role === 'passenger' && m.status !== 'cancelled')

  return (
    <div className="grid gap-4">
      <section className={`rounded-xl p-5 ${toneBox[tone]}`}>
        <h1 className="text-2xl font-semibold leading-tight tracking-tight">{stage.headline}</h1>
        <p className="mt-1.5 text-[17px] opacity-90">{stage.detail}</p>
        <Progress code={stage.code} />
      </section>

      {journey.disruption && journey.status !== 'normal' && (
        <p className="flex items-start gap-2 text-[15px] text-px-muted">
          <TriangleAlert size={17} className="mt-0.5 shrink-0" /> {journey.disruption.description}
        </p>
      )}

      {canChoose && journey.preferences.length === 0 && (
        <Link to={`/app/journey/${journey.id}/options`}>
          <Button className="w-full">Compare my options <ArrowRight size={18} /></Button>
        </Link>
      )}

      {journey.allocation && <Ticket journey={journey} onChange={onChange} />}

      {myMatches.map((m) => <MatchCard key={m.id} match={m} onChange={onChange} />)}

      {journey.preferences.length > 0 && journey.status === 'affected' && (
        <Card>
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-semibold">Your preferences</h3>
            <Pill tone="neutral">Not a booking</Pill>
          </div>
          <ol className="mt-3 grid gap-2">
            {journey.preferences.map((p: any) => (
              <li key={p.rank} className="flex items-start gap-3 text-[15px]">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-px-accent-soft text-sm font-semibold text-px-accent">{p.rank}</span>
                <span>
                  {p.title}
                  <span className="block text-sm text-px-muted">{p.status === 'invalidated' ? 'No longer available, please choose again' : p.availability.label}</span>
                </span>
              </li>
            ))}
          </ol>
          {canChoose && <Link to={`/app/journey/${journey.id}/options`} className="mt-3 inline-block text-[15px] font-medium text-px-accent underline underline-offset-2">Change my choices</Link>}
        </Card>
      )}

      {stage.code === 'carpool_listed' && (
        <Card>
          <h3 className="flex items-center gap-2 font-semibold"><Car size={18} className="text-px-accent" /> You're on a community carpool listing</h3>
          <p className="mt-1 text-[15px] text-px-muted">
            Drivers already heading your way can see your area, destination and party size, but never your name or number. Nothing happens without your say-so.
          </p>
          <Button variant="quiet" className="mt-2" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/leave-carpool`).then(onChange), "You've left the carpool listing")}>Leave the listing</Button>
        </Card>
      )}
      {journey.carpool_opt_out && journey.status === 'affected' && (
        <Button variant="secondary" disabled={busy} onClick={() => run(() => pxApi.post(`/me/journeys/${journey.id}/join-carpool`).then(onChange), 'Back on the carpool listing')}>Rejoin the carpool listing</Button>
      )}

      <Card>
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold">Your journey</h3>
          <span className="text-sm text-px-muted">{journey.ref}</span>
        </div>
        <ul className="mt-2 grid gap-1.5 text-[15px]">
          <li className="flex items-center gap-2"><MapPin size={16} className="text-px-muted" /> {journey.origin} to {journey.destination}</li>
          <li className="flex items-center gap-2"><Clock size={16} className="text-px-muted" /> Leaving {hhmm(journey.dep_earliest)}–{hhmm(journey.dep_latest)}, arrive by {hhmm(journey.latest_arrival)}</li>
          <li className="text-px-muted">{plural(journey.party_size, 'person', 'people')}{journey.requirements.length ? ` · ${journey.requirements.map((r: string) => REQUIREMENT_LABEL[r]).join(', ')}` : ''}{journey.booked_service_id ? ` · Booked on ${journey.booked_service_id}` : ''}</li>
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

export default function Home() {
  const { data: journeys, error, refetch } = useLive(pxApi, '/me/journeys')
  const { data: matches, refetch: refetchMatches } = useLive(pxApi, '/carpool/matches/mine')
  const { data: disruptions } = useLive(pxApi, '/me/disruptions')
  const { data: me } = useLive(pxApi, '/auth/me')
  if (!journeys) return <p className="py-10 text-center text-px-muted">{error ?? 'Loading your journey…'}</p>

  const refresh = () => {
    refetch()
    refetchMatches()
  }
  const driving = (matches ?? []).filter((m: any) => m.role === 'provider' && m.status !== 'cancelled')

  return (
    <div className="grid gap-6">
      {journeys.length === 0 && (
        <section>
          <h1 className="text-2xl font-semibold tracking-tight">Hello{me ? `, ${me.name.split(' ')[0]}` : ''}</h1>
          <p className="mt-1 text-px-muted">You have no journeys registered.</p>
        </section>
      )}

      {disruptions?.length > 0 && journeys.every((j: any) => j.status === 'normal') && (
        <Card className="border-px-warn/30">
          <h2 className="flex items-center gap-2 font-semibold"><TriangleAlert size={18} className="text-px-warn" /> Current disruptions</h2>
          <ul className="mt-2 grid gap-1 text-[15px]">
            {disruptions.map((d: any) => <li key={d.code}>{d.description}</li>)}
          </ul>
        </Card>
      )}

      {journeys.map((j: any) => <JourneyCard key={j.id} journey={j} matches={matches ?? []} onChange={refresh} />)}

      {driving.length > 0 && (
        <section className="grid gap-3">
          <h2 className="text-lg font-semibold">Rides you're offering</h2>
          {driving.map((m: any) => <MatchCard key={m.id} match={m} onChange={refresh} />)}
        </section>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Link to="/app/journey/new" className="rounded-xl border border-px-line bg-px-card p-4 hover:border-px-accent">
          <p className="font-semibold">Register a journey</p>
          <p className="text-[15px] text-px-muted">Tell us where you need to be.</p>
        </Link>
        <Link to="/app/carpool" className="rounded-xl border border-px-line bg-px-card p-4 hover:border-px-accent">
          <p className="font-semibold">Offer a spare seat</p>
          <p className="text-[15px] text-px-muted">Already heading that way? Help someone out.</p>
        </Link>
      </div>
    </div>
  )
}
