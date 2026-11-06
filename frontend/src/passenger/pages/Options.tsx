import { ArrowLeft, ArrowRight, ArrowUpDown, Bus, Clock, Footprints, Info, ListOrdered, MapPinned, Repeat, Star, Ticket, Timer, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { pxApi, useLive } from '../../lib/api'
import { hhmm } from '../../lib/format'
import { Button, Card, Eyebrow, IconTile, Pill, useDo, type Tone } from '../ui'

const KIND: Record<string, { label: string; icon: LucideIcon }> = {
  replacement: { label: 'Replacement vehicle', icon: Bus },
  different_pickup: { label: 'Replacement, different pickup', icon: MapPinned },
  later_departure: { label: 'Regular service', icon: Clock },
  transfer: { label: 'With one change', icon: Repeat },
}

const AVAIL_TONE: Record<string, Tone> = { available: 'good', walk_up: 'neutral', full: 'warn', unavailable: 'bad' }

function Spec({ icon: Icon, children }: { icon: LucideIcon; children: string }) {
  return <li className="flex min-w-0 items-start gap-1.5"><Icon size={16} className="mt-0.5 shrink-0 text-px-muted" aria-hidden="true" /> {children}</li>
}

function OptionCard({ o, rank, onRank, disabled }: { o: any; rank: number | null; onRank: (r: 1 | 2) => void; disabled: boolean }) {
  const kind = KIND[o.kind]
  return (
    <Card className={rank === 1 ? 'ring-2 ring-px-accent' : rank === 2 ? 'ring-2 ring-px-highest' : ''}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {rank ? (
          <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[13px] font-semibold ${rank === 1 ? 'bg-px-accent text-white' : 'bg-px-highest text-px-accent'}`}>
            <Star size={14} aria-hidden="true" /> Rank #{rank} choice
          </span>
        ) : <span className="text-sm text-px-muted">{kind.label}</span>}
        <Pill tone={AVAIL_TONE[o.availability.code]}>{o.availability.label}</Pill>
      </div>

      <div className="mt-3 flex items-start gap-3">
        <IconTile icon={kind.icon} className="size-14 rounded-xl" />
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-snug">{o.title}</h2>
          <p className="num flex flex-wrap items-center gap-x-1.5 font-semibold text-px-accent">
            <Clock size={16} aria-hidden="true" /> {hhmm(o.departure)} to {hhmm(o.arrival)}
            <span className="font-normal text-px-muted">({o.duration} min)</span>
          </p>
        </div>
      </div>

      {!o.meets_deadline && <p className="mt-2 rounded-xl bg-px-warn-soft px-3 py-2 text-[15px] font-medium text-px-warn">Arrives after your latest arrival time</p>}

      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-xl bg-px-low p-3 text-sm">
        <Spec icon={Timer}>{`${o.wait_min} min wait`}</Spec>
        <Spec icon={Footprints}>{o.walk_m ? `${o.walk_m} m walk` : 'No walk'}</Spec>
        <Spec icon={Repeat}>{o.transfers ? `${o.transfers} change` : 'Direct'}</Spec>
        <Spec icon={Ticket}>{o.reservable ? 'Seat can be reserved' : 'No reservation'}</Spec>
      </ul>

      {o.legs.length > 1 && (
        <ol className="mt-2 grid gap-0.5 rounded-xl bg-px-mid px-3 py-2 text-sm">
          {o.legs.map((l: any, i: number) => <li key={i}><span className="num font-semibold">{hhmm(l.depart)}</span> {l.name}: {l.from} to {l.to}</li>)}
        </ol>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label={`Rank ${o.title}`}>
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
    <div className="grid gap-4">
      <Link to="/app" className="inline-flex min-h-11 items-center gap-1 text-[15px] text-px-muted hover:text-px-ink"><ArrowLeft size={16} /> My journey</Link>

      <section className="rounded-2xl bg-px-mid p-5">
        <Eyebrow>Your options</Eyebrow>
        {journey ? (
          <>
            <h1 className="mt-1 text-2xl font-semibold leading-tight tracking-tight">{journey.origin} to {journey.destination}</h1>
            <p className="num mt-3 flex items-center gap-2 rounded-xl bg-px-high px-3 py-2 text-[15px]">
              <Timer size={18} className="shrink-0 text-px-accent" /> Arriving by <span className="font-semibold">{hhmm(journey.latest_arrival)}</span>
            </p>
          </>
        ) : <h1 className="mt-1 text-2xl font-semibold tracking-tight">Your options</h1>}
      </section>

      <section className="flex items-start gap-3 rounded-2xl bg-px-low p-4">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-px-highest text-px-accent"><Info size={17} aria-hidden="true" /></span>
        <div className="min-w-0">
          <p className="font-semibold">Choosing isn't booking.</p>
          <p className="text-[15px] text-px-muted">These are suggestions. Your choices help the operator plan, and a seat is only yours when we tell you it's confirmed.</p>
        </div>
      </section>

      {error && <p className="text-px-bad">{error}</p>}
      {options?.length === 0 && (
        <Card>
          <h2 className="text-lg font-semibold">No suggestions right now</h2>
          <p className="mt-1 text-[15px] text-px-muted">We couldn't find anything that fits your journey yet. The operator can see you're waiting, and we'll update you.</p>
        </Card>
      )}
      {options?.length > 0 && (
        <div className="flex items-center justify-between gap-3 px-1">
          <Eyebrow className="flex items-center gap-1.5 text-px-ink"><ListOrdered size={16} className="text-px-accent" /> Rank your choices</Eyebrow>
          <span className="text-sm text-px-muted">Pick a 1st and a 2nd</span>
        </div>
      )}
      {options?.map((o: any) => (
        <OptionCard key={o.id} o={o} rank={first === o.id ? 1 : second === o.id ? 2 : null} onRank={(r) => rank(o.id, r)} disabled={!!locked} />
      ))}

      {!locked && options?.length > 0 && (
        <div className="fixed inset-x-0 bottom-16 z-20 bg-px-card shadow-tray md:bottom-0">
          <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3">
            <div className="flex min-w-0 items-center gap-2">
              {first && second ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full bg-px-highest px-4 text-sm font-semibold hover:bg-px-high"
                  onClick={() => {
                    setFirst(second)
                    setSecond(first)
                  }}
                >
                  <ArrowUpDown size={16} className="text-px-accent" /> Swap order
                </button>
              ) : <p className="text-[15px] text-px-muted">{first ? 'Add a second choice if you can' : 'Pick your 1st choice'}</p>}
            </div>
            <Button
              disabled={busy || !first}
              onClick={async () => {
                const ok = await run(() => pxApi.put(`/me/journeys/${id}/preferences`, { first_option_id: first, second_option_id: second }), "Thanks. The operator can see your choices now.")
                if (ok) navigate('/app')
              }}
            >
              Send my choices <ArrowRight size={18} />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
