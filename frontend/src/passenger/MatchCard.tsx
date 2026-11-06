import { Car, Check, Clock, Lock, Phone, Route, ShieldAlert, Star, Users, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { pxApi } from '../lib/api'
import { hhmm, plural, REQUIREMENT_LABEL } from '../lib/format'
import { Button, Card, Field, IconTile, Pill, toneBox, useDo, type Tone } from './ui'

const STATUS: Record<string, [string, Tone]> = {
  awaiting_passenger: ['Awaiting passenger acceptance', 'info'],
  awaiting_provider: ['Awaiting driver confirmation', 'info'],
  confirmed: ['Confirmed', 'good'],
  completed: ['Completed', 'neutral'],
  cancelled: ['Cancelled', 'neutral'],
}

function Fact({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-px-high text-px-accent"><Icon size={16} aria-hidden="true" /></span>
      <div className="min-w-0">
        <dt className="text-sm font-semibold">{label}</dt>
        <dd className="text-[15px] text-px-muted">{children}</dd>
      </div>
    </div>
  )
}

export default function MatchCard({ match, onChange }: { match: any; onChange: () => void }) {
  const { busy, run } = useDo()
  const [reporting, setReporting] = useState(false)
  const [reason, setReason] = useState('')
  const provider = match.role === 'provider'
  const [label, tone] = STATUS[match.status]
  const url = `/carpool/matches/${match.id}`
  const live = ['awaiting_passenger', 'awaiting_provider', 'confirmed'].includes(match.status)
  const answer = (path: string, accept: boolean, message: string) =>
    run(() => pxApi.post(`${url}/${path}`, { accept }).then(onChange), message)

  return (
    <Card flush>
      <p className={`px-5 py-2.5 text-xs font-semibold uppercase tracking-wider ${match.status === 'confirmed' ? 'bg-px-good-strong text-white' : toneBox[tone]}`}>{label}</p>

      <div className="p-5">
        <div className="flex items-start gap-3">
          <IconTile icon={Car} className="size-14" />
          <div className="min-w-0">
            <p className="text-sm text-px-muted">{provider ? 'Your offer' : 'Community ride'} · {match.label}</p>
            <h3 className="text-lg font-semibold leading-snug">{match.pickup_area} to {match.destination}</h3>
          </div>
        </div>

        {!provider && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Pill tone="info"><Star size={13} aria-hidden="true" /> {plural(match.provider_trust.rides_completed, 'ride')} completed</Pill>
            <Pill tone="neutral">Member since {match.provider_trust.member_since}</Pill>
            <Pill tone="warn">Not verified by us</Pill>
          </div>
        )}

        <dl className="mt-4 grid gap-3 rounded-xl bg-px-low p-4">
          <Fact icon={Clock} label="Pickup around"><span className="num">{hhmm(match.pickup_min)}</span></Fact>
          <Fact icon={Users} label="Seats"><span className="num">{match.matched_seats}</span></Fact>
          <Fact icon={Car} label="Vehicle">{match.vehicle_type}</Fact>
          {provider && <Fact icon={Route} label="Extra driving"><span className="num">{match.detour_min}</span> min</Fact>}
        </dl>

        {provider && (
          <div className="mt-3 text-[15px]">
            <p className="text-sm font-semibold">Passengers</p>
            <ul>
              {match.parties.map((p: any, i: number) => (
                <li key={i} className="flex items-center justify-between gap-2 py-0.5">
                  <span>{plural(p.seats, 'person', 'people')}{p.requirements.length ? `, ${p.requirements.map((r: string) => REQUIREMENT_LABEL[r].toLowerCase()).join(', ')}` : ''}</span>
                  <span className="text-sm text-px-muted">{p.acceptance === 'accepted' ? 'Accepted' : p.acceptance === 'declined' ? 'Declined' : 'Deciding'}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {match.contact ? (
          <div className="mt-3 rounded-xl bg-px-good-soft p-4">
            <p className="text-sm font-semibold text-px-good">Shared now that everyone has agreed</p>
            <p className="mt-1 font-semibold">Exact pickup: {match.pickup_stop}</p>
            {match.contact.map((c: any) => (
              <p key={c.phone} className="mt-0.5 flex items-center gap-2 text-[15px]"><Phone size={14} /> {c.name}, {c.phone}{provider ? ` (${plural(c.seats, 'seat')})` : ''}</p>
            ))}
          </div>
        ) : live && (
          <div className="mt-3 rounded-xl bg-px-mid p-4">
            <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-px-accent"><Lock size={15} aria-hidden="true" /> Private until you both agree</p>
            <p className="mt-1 text-[15px] text-px-muted">Names, phone numbers and the exact pickup stay private until both sides confirm.</p>
          </div>
        )}

        {match.status === 'cancelled' && match.cancel_reason && <p className="mt-3 text-[15px] text-px-muted">{match.cancel_reason}</p>}

        <div className="mt-4 grid gap-2">
          {!provider && match.status === 'awaiting_passenger' && match.my_acceptance === 'pending' && (
            <>
              <Button disabled={busy} onClick={() => answer('passenger-response', true, "Accepted. We've asked the driver to confirm.")}><Check size={17} /> Accept this ride</Button>
              <Button variant="secondary" disabled={busy} onClick={() => answer('passenger-response', false, "Declined. You're still on the listing.")}>No thanks</Button>
            </>
          )}
          {!provider && match.status === 'awaiting_passenger' && match.my_acceptance === 'accepted' && (
            <p className="text-[15px] text-px-muted">You've accepted. Waiting for the other passengers.</p>
          )}
          {provider && match.status === 'awaiting_passenger' && <p className="text-[15px] text-px-muted">Passengers are reviewing this. We'll ask you to confirm next.</p>}
          {provider && match.status === 'awaiting_provider' && (
            <>
              <Button disabled={busy} onClick={() => answer('provider-response', true, 'Ride confirmed. Contact details are now visible.')}><Check size={17} /> Confirm this ride</Button>
              <Button variant="secondary" disabled={busy} onClick={() => answer('provider-response', false, 'Proposal rejected')}>Can't do it</Button>
            </>
          )}
          {provider && match.status === 'confirmed' && (
            <Button variant="secondary" disabled={busy} onClick={() => run(() => pxApi.post(`${url}/complete`).then(onChange), 'Ride marked as complete. Thank you!')}>Mark ride complete</Button>
          )}
          {match.status === 'confirmed' && (
            <Button variant="danger" disabled={busy} onClick={() => run(() => pxApi.post(`${url}/cancel`, { reason: provider ? 'Driver cancelled' : 'Passenger cancelled' }).then(onChange), 'Ride cancelled')}>Cancel ride</Button>
          )}
          {(live || match.status === 'completed') && (
            <Button variant="quiet" onClick={() => setReporting(!reporting)}><ShieldAlert size={14} /> Report a problem</Button>
          )}
        </div>

        {reporting && (
          <form
            className="mt-3 grid gap-2"
            onSubmit={async (e) => {
              e.preventDefault()
              if (await run(() => pxApi.post(`${url}/report`, { reason }), 'Report sent to the operator')) {
                setReporting(false)
                setReason('')
              }
            }}
          >
            <Field label="What happened?"><textarea rows={2} required minLength={3} className="px-input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <Button type="submit" variant="secondary" disabled={busy}>Send report</Button>
          </form>
        )}
      </div>
    </Card>
  )
}
