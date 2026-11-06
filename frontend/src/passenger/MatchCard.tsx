import { Check, Phone, ShieldAlert, Star } from 'lucide-react'
import { useState } from 'react'
import { pxApi } from '../lib/api'
import { hhmm, plural, REQUIREMENT_LABEL } from '../lib/format'
import { Button, Card, Field, Pill, useDo, type Tone } from './ui'

const STATUS: Record<string, [string, Tone]> = {
  awaiting_passenger: ['Awaiting passenger acceptance', 'info'],
  awaiting_provider: ['Awaiting driver confirmation', 'info'],
  confirmed: ['Confirmed', 'good'],
  completed: ['Completed', 'neutral'],
  cancelled: ['Cancelled', 'neutral'],
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
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm text-px-muted">{provider ? 'Your offer' : 'Community ride'} · {match.label}</p>
          <h3 className="text-lg font-semibold leading-snug">{match.pickup_area} to {match.destination}</h3>
        </div>
        <Pill tone={tone}>{label}</Pill>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 text-[15px] sm:grid-cols-3">
        <div><dt className="text-sm text-px-muted">Pickup around</dt><dd className="font-medium">{hhmm(match.pickup_min)}</dd></div>
        <div><dt className="text-sm text-px-muted">Seats</dt><dd className="font-medium">{match.matched_seats}</dd></div>
        <div><dt className="text-sm text-px-muted">Vehicle</dt><dd className="font-medium">{match.vehicle_type}</dd></div>
        {provider && <div><dt className="text-sm text-px-muted">Extra driving</dt><dd className="font-medium">{match.detour_min} min</dd></div>}
      </dl>

      {provider ? (
        <div className="mt-3 text-[15px]">
          <p className="text-sm text-px-muted">Passengers</p>
          <ul>
            {match.parties.map((p: any, i: number) => (
              <li key={i} className="flex items-center justify-between gap-2 py-0.5">
                <span>{plural(p.seats, 'person', 'people')}{p.requirements.length ? `, ${p.requirements.map((r: string) => REQUIREMENT_LABEL[r].toLowerCase()).join(', ')}` : ''}</span>
                <span className="text-sm text-px-muted">{p.acceptance === 'accepted' ? 'Accepted' : p.acceptance === 'declined' ? 'Declined' : 'Deciding'}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 flex items-center gap-1.5 text-[15px]">
          <Star size={15} className="text-px-accent" />
          {plural(match.provider_trust.rides_completed, 'ride')} completed on the platform · member since {match.provider_trust.member_since}
        </p>
      )}

      {match.contact ? (
        <div className="mt-4 rounded-lg bg-px-accent-soft p-3">
          <p className="text-sm font-medium text-px-accent">Shared now that everyone has agreed</p>
          <p className="mt-1 font-medium">Exact pickup: {match.pickup_stop}</p>
          {match.contact.map((c: any) => (
            <p key={c.phone} className="mt-0.5 flex items-center gap-2 text-[15px]"><Phone size={14} /> {c.name}, {c.phone}{provider ? ` (${plural(c.seats, 'seat')})` : ''}</p>
          ))}
        </div>
      ) : live && (
        <p className="mt-3 text-sm text-px-muted">Names, phone numbers and the exact pickup stay private until both sides confirm.</p>
      )}

      {match.status === 'cancelled' && match.cancel_reason && <p className="mt-3 text-[15px] text-px-muted">{match.cancel_reason}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
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
    </Card>
  )
}
