import { ArrowLeft, Footprints, Repeat, Ticket, Timer } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { pxApi, useLive } from '../../lib/api'
import { hhmm } from '../../lib/format'
import { Button, Card, Pill, useDo, type Tone } from '../ui'

const KIND: Record<string, string> = {
  replacement: 'Replacement vehicle',
  different_pickup: 'Replacement, different pickup',
  later_departure: 'Regular service',
  transfer: 'With one change',
}

const AVAIL_TONE: Record<string, Tone> = { available: 'good', walk_up: 'neutral', full: 'warn', unavailable: 'bad' }

function OptionCard({ o, rank, onRank, disabled }: { o: any; rank: number | null; onRank: (r: 1 | 2) => void; disabled: boolean }) {
  return (
    <Card className={rank ? 'border-px-accent outline outline-1 outline-px-accent' : ''}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm text-px-muted">{KIND[o.kind]}</p>
          <h2 className="font-semibold leading-snug">{o.title}</h2>
        </div>
        <Pill tone={AVAIL_TONE[o.availability.code]}>{o.availability.label}</Pill>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl font-semibold tracking-tight">{hhmm(o.departure)}</span>
        <span className="text-px-muted">to</span>
        <span className="text-2xl font-semibold tracking-tight">{hhmm(o.arrival)}</span>
        <span className="text-[15px] text-px-muted">{o.duration} min</span>
      </div>

      {!o.meets_deadline && <p className="mt-1 text-[15px] font-medium text-px-warn">Arrives after your latest arrival time</p>}

      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[15px] text-px-muted">
        <li className="flex items-center gap-1.5"><Timer size={15} /> {o.wait_min} min wait</li>
        <li className="flex items-center gap-1.5"><Footprints size={15} /> {o.walk_m ? `${o.walk_m} m walk` : 'No walk'}</li>
        <li className="flex items-center gap-1.5"><Repeat size={15} /> {o.transfers ? `${o.transfers} change` : 'Direct'}</li>
        <li className="flex items-center gap-1.5"><Ticket size={15} /> {o.reservable ? 'Seat can be reserved' : 'No reservation'}</li>
      </ul>

      {o.legs.length > 1 && (
        <ol className="mt-2 text-[15px]">
          {o.legs.map((l: any, i: number) => <li key={i}>{hhmm(l.depart)} {l.name}: {l.from} to {l.to}</li>)}
        </ol>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2" role="group" aria-label={`Rank ${o.title}`}>
        {([1, 2] as const).map((r) => (
          <Button key={r} variant={rank === r ? 'primary' : 'secondary'} aria-pressed={rank === r} disabled={disabled} onClick={() => onRank(r)}>
            {r === 1 ? '1st choice' : '2nd choice'}
          </Button>
        ))}
      </div>
    </Card>
  )
}

export default function Options() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: options, error } = useLive(pxApi, `/me/journeys/${id}/options`)
  const { data: journeys } = useLive(pxApi, '/me/journeys')
  const { busy, run } = useDo()
  const journey = journeys?.find((j: any) => String(j.id) === id)
  const [first, setFirst] = useState<number | null>(null)
  const [second, setSecond] = useState<number | null>(null)
  const [seeded, setSeeded] = useState(false)

  useEffect(() => {
    if (journey && !seeded) {
      setFirst(journey.preferences.find((p: any) => p.rank === 1 && p.status !== 'invalidated')?.option_id ?? null)
      setSecond(journey.preferences.find((p: any) => p.rank === 2 && p.status !== 'invalidated')?.option_id ?? null)
      setSeeded(true)
    }
  }, [journey, seeded])

  const rank = (optionId: number, r: 1 | 2) => {
    if (r === 1) {
      setFirst(first === optionId ? null : optionId)
      if (second === optionId) setSecond(null)
    } else {
      setSecond(second === optionId ? null : optionId)
      if (first === optionId) setFirst(null)
    }
  }

  const locked = journey?.preferences_locked

  return (
    <div className="grid gap-4 pb-24">
      <Link to="/app" className="inline-flex items-center gap-1 text-[15px] text-px-muted hover:text-px-ink"><ArrowLeft size={16} /> My journey</Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Your options</h1>
        {journey && <p className="mt-1 text-px-muted">{journey.origin} to {journey.destination}, arriving by {hhmm(journey.latest_arrival)}</p>}
      </div>

      <p className="rounded-lg bg-px-info-soft px-4 py-3 text-[15px] text-px-info">
        <strong className="font-semibold">Choosing isn't booking.</strong> These are suggestions. Your choices help the operator plan, and a seat is only yours when we tell you it's confirmed.
      </p>

      {error && <p className="text-px-bad">{error}</p>}
      {options?.length === 0 && (
        <Card>
          <h2 className="font-semibold">No suggestions right now</h2>
          <p className="mt-1 text-[15px] text-px-muted">We couldn't find anything that fits your journey yet. The operator can see you're waiting, and we'll update you.</p>
        </Card>
      )}
      {options?.map((o: any) => (
        <OptionCard key={o.id} o={o} rank={first === o.id ? 1 : second === o.id ? 2 : null} onRank={(r) => rank(o.id, r)} disabled={!!locked} />
      ))}

      {!locked && options?.length > 0 && (
        <div className="fixed inset-x-0 bottom-14 z-20 border-t border-px-line bg-px-card/95 md:bottom-0">
          <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
            <p className="text-[15px] text-px-muted">{first ? (second ? 'Both choices selected' : 'Add a second choice if you can') : 'Pick your 1st choice'}</p>
            <Button
              disabled={busy || !first}
              onClick={async () => {
                const ok = await run(() => pxApi.put(`/me/journeys/${id}/preferences`, { first_option_id: first, second_option_id: second }), "Thanks. The operator can see your choices now.")
                if (ok) navigate('/app')
              }}
            >
              Send my choices
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
