import { useState } from 'react'
import { Link } from 'react-router-dom'
import { opApi, useLive } from '../../lib/api'
import { hhmm, REQUIREMENT_LABEL } from '../../lib/format'
import { Badge, Btn, Empty, Loading, PageHeader, Panel, ReasonDialog, useAction } from '../ui'
import { OverridePanel } from './Passengers'

function ReviewRow({ a, onDone }: { a: any; onDone: () => void }) {
  const { data: options } = useLive(opApi, `/op/allocations/${a.id}/vehicle-options`)
  const { busy, run } = useAction()
  const [dialog, setDialog] = useState<null | { kind: 'keep' | 'release' | 'reassign'; vehicle?: string }>(null)
  const targets = options?.filter((o: any) => o.overridable) ?? []
  return (
    <tr>
      <td className="num">{a.ref}</td>
      <td className="num">{a.party_size}</td>
      <td className="num">{a.vehicle_id}</td>
      <td className="text-op-muted">{a.flag_reason}</td>
      <td>{a.seats_held ? <Badge tone="good">Seat held</Badge> : <Badge tone="bad">No physical seat</Badge>}</td>
      <td>
        <div className="flex flex-wrap justify-end gap-1">
          <Btn disabled={busy || !a.seats_held} onClick={() => setDialog({ kind: 'keep' })}>Keep</Btn>
          {targets.map((o: any) => (
            <Btn key={o.vehicle_id} disabled={busy} onClick={() => setDialog({ kind: 'reassign', vehicle: o.vehicle_id })}>Move to {o.vehicle_id}</Btn>
          ))}
          <Btn variant="danger" disabled={busy} onClick={() => setDialog({ kind: 'release' })}>Release</Btn>
        </div>
        {dialog && (
          <ReasonDialog
            title={dialog.kind === 'keep' ? `Keep ${a.ref} on ${a.vehicle_id}` : dialog.kind === 'reassign' ? `Move ${a.ref} to ${dialog.vehicle}` : `Release ${a.ref}`}
            body={dialog.kind === 'release' ? 'The party returns to unresolved demand and to the carpool listings.' : undefined}
            confirmLabel="Confirm"
            danger={dialog.kind === 'release'}
            onCancel={() => setDialog(null)}
            onConfirm={(reason) => {
              const d = dialog
              setDialog(null)
              const action = d.kind === 'keep' ? opApi.post(`/op/allocations/${a.id}/keep`, { reason })
                : d.kind === 'reassign' ? opApi.post(`/op/allocations/${a.id}/reassign`, { vehicle_id: d.vehicle, reason })
                : opApi.post(`/op/allocations/${a.id}/reject`, { reason })
              run(() => action.then(onDone), 'Decision recorded and passenger notified')
            }}
          />
        )}
      </td>
    </tr>
  )
}

export default function Unresolved() {
  const { data, error, refetch } = useLive(opApi, '/op/unresolved')
  const [assigning, setAssigning] = useState<any>(null)
  const { busy, run } = useAction()
  if (!data) return <Loading error={error} />

  return (
    <>
      <PageHeader
        title="Unresolved demand"
        sub={`${data.passengers} passengers in ${data.parties.length} parties have no official seat in play.`}
        action={<Btn disabled={busy} onClick={() => run(() => opApi.post('/op/carpool/publish').then(refetch), 'Carpool listings refreshed')}>Refresh carpool listings</Btn>}
      />

      {data.needs_review.length > 0 && (
        <Panel title={<span className="text-op-signal">Confirmed journeys needing a decision</span>} flush className="mb-3">
          <table className="op-table">
            <thead><tr><th>Party</th><th>Seats</th><th>Vehicle</th><th>Why flagged</th><th>Seat</th><th /></tr></thead>
            <tbody>{data.needs_review.map((a: any) => <ReviewRow key={a.id} a={a} onDone={refetch} />)}</tbody>
          </table>
        </Panel>
      )}

      <div className={`grid gap-3 ${assigning ? 'xl:grid-cols-[1fr_300px]' : ''}`}>
        <Panel title="Waiting parties" flush>
          {data.parties.length ? (
            <table className="op-table">
              <thead><tr><th>Party</th><th>Size</th><th>Journey</th><th>Arrive by</th><th>Why no seat</th><th>Other options</th><th>Carpool</th><th /></tr></thead>
              <tbody>
                {data.parties.map((p: any) => (
                  <tr key={p.id}>
                    <td className="num">{p.ref}</td>
                    <td className="num">{p.party_size}</td>
                    <td className="whitespace-nowrap">
                      {p.origin} → {p.destination}
                      {p.requirements.length > 0 && <span className="block text-[11px] text-op-signal">{p.requirements.map((r: string) => REQUIREMENT_LABEL[r]).join(', ')}</span>}
                    </td>
                    <td className="num">{hhmm(p.latest_arrival)}</td>
                    <td className="max-w-80 text-op-muted">{p.reason}</td>
                    <td className="num">{p.usable_alternatives ? `${p.usable_alternatives} in time` : <span className="text-op-bad">None in time</span>}</td>
                    <td className="whitespace-nowrap">{p.opted_out ? <span className="text-op-muted">Opted out</span> : p.carpool_listing ? <Link to="/operator/carpool" className="num text-op-info">{p.carpool_listing}</Link> : <span className="text-op-faint">Not listed</span>}</td>
                    <td className="text-right"><Btn onClick={() => setAssigning(p)}>Assign</Btn></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>No unresolved passengers.</Empty>}
        </Panel>
        {assigning && <OverridePanel key={assigning.id} journey={assigning} onClose={() => setAssigning(null)} />}
      </div>
    </>
  )
}
