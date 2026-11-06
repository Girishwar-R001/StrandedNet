import { Check, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { hhmm, REQUIREMENT_LABEL } from '../../lib/format'
import { Btn, Empty, Loading, PageHeader, Panel, ReasonDialog, StateBadge, useAction } from '../ui'

export function OverridePanel({ journey, onClose }: { journey: any; onClose: () => void }) {
  const { data: options } = useLive(opApi, `/op/journeys/${journey.id}/vehicle-options`)
  const { busy, run } = useAction()
  const [target, setTarget] = useState<string | null>(null)
  return (
    <Panel title={`${journey.ref} vehicle feasibility`} action={<Btn variant="ghost" onClick={onClose} aria-label="Close"><X size={14} /></Btn>}>
      <div className="grid gap-3">
        {options?.map((o: any) => (
          <div key={o.vehicle_id}>
            <div className="flex items-center justify-between gap-2">
              <span className="num text-xs">{o.vehicle_id} <span className="text-op-muted">{o.seats_left} left</span></span>
              <Btn disabled={busy || !o.overridable} onClick={() => setTarget(o.vehicle_id)} title={o.overridable ? '' : 'Hard constraints cannot be overridden'}>Assign</Btn>
            </div>
            <ul className="mt-1 grid gap-0.5">
              {o.checks.map((c: any) => (
                <li key={c.name} className="flex gap-1.5 text-[11px] text-op-muted">
                  {c.ok ? <Check size={12} className="mt-px shrink-0 text-op-good" /> : <X size={12} className="mt-px shrink-0 text-op-bad" />}
                  {c.detail}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p className="text-[11px] text-op-faint">Overrides can bypass timing and ranking. Seats, accessibility and routing can never be overridden.</p>
      </div>
      {target && (
        <ReasonDialog
          title={`Assign ${journey.ref} to ${target}`}
          body="Reserves seats immediately and bypasses the engine's ranking."
          confirmLabel="Assign and reserve"
          onCancel={() => setTarget(null)}
          onConfirm={(reason) => {
            const vehicle_id = target
            setTarget(null)
            run(() => opApi.post('/op/allocations/override', { journey_id: journey.id, vehicle_id, reason }).then(onClose), `${journey.ref} assigned to ${vehicle_id}`)
          }}
        />
      )}
    </Panel>
  )
}

export default function Passengers() {
  const { data, error } = useLive(opApi, '/op/passengers?scope=all')
  const [query, setQuery] = useState('')
  const [state, setState] = useState('affected')
  const [selected, setSelected] = useState<number | null>(null)

  const rows = useMemo(() => {
    const q = query.toLowerCase()
    return (data ?? []).filter((p: any) => {
      if (state === 'affected' && p.state === 'unaffected') return false
      if (state !== 'affected' && state !== 'all' && p.state !== state) return false
      return !q || `${p.ref} ${p.name} ${p.origin} ${p.destination}`.toLowerCase().includes(q)
    })
  }, [data, query, state])

  if (!data) return <Loading error={error} />
  const picked = data.find((p: any) => p.id === selected)
  const seats = rows.reduce((sum: number, p: any) => sum + p.party_size, 0)

  return (
    <>
      <PageHeader
        title="Passenger management"
        sub={`${rows.length} parties, ${seats} passengers shown.`}
        action={
          <>
            <input className="op-input w-44" placeholder="Search" aria-label="Search passengers" value={query} onChange={(e) => setQuery(e.target.value)} />
            <select className="op-input" aria-label="Filter by status" value={state} onChange={(e) => setState(e.target.value)}>
              <option value="affected">All affected</option>
              <option value="all">Everyone</option>
              <option value="unresolved">Unresolved</option>
              <option value="proposed">Proposed</option>
              <option value="official_confirmed">Seat confirmed</option>
              <option value="carpool_confirmed">Carpool confirmed</option>
              <option value="needs_review">Needs review</option>
            </select>
          </>
        }
      />
      <div className={`grid gap-3 ${picked ? 'xl:grid-cols-[1fr_300px]' : ''}`}>
        <Panel flush>
          {rows.length ? (
            <table className="op-table">
              <thead>
                <tr><th>Ref</th><th>Lead passenger</th><th>Party</th><th>From</th><th>To</th><th>Departure</th><th>Arrive by</th><th>Needs</th><th>Group</th><th>Status</th></tr>
              </thead>
              <tbody>
                {rows.map((p: any) => (
                  <tr key={p.id} className="row-link" onClick={() => setSelected(p.id === selected ? null : p.id)}>
                    <td className="num">{p.ref}</td>
                    <td className="whitespace-nowrap">{p.name}</td>
                    <td className="num">{p.party_size}</td>
                    <td className="whitespace-nowrap text-op-muted">{p.origin}</td>
                    <td className="whitespace-nowrap text-op-muted">{p.destination}</td>
                    <td className="num whitespace-nowrap">{hhmm(p.dep_earliest)}–{hhmm(p.dep_latest)}</td>
                    <td className="num">{hhmm(p.latest_arrival)}</td>
                    <td className="whitespace-nowrap text-op-muted">{p.requirements.map((r: string) => REQUIREMENT_LABEL[r]).join(', ') || '–'}</td>
                    <td className="num text-op-muted">{p.group ?? '–'}</td>
                    <td><StateBadge state={p.state} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>{data.some((p: any) => p.state !== 'unaffected') ? 'No passengers match this filter.' : 'Nobody is affected. Trigger a disruption to see passengers here.'}</Empty>}
        </Panel>
        {picked && <OverridePanel key={picked.id} journey={picked} onClose={() => setSelected(null)} />}
      </div>
    </>
  )
}
