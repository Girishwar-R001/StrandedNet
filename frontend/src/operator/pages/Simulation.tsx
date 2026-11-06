import { Play, RotateCcw, UsersRound } from 'lucide-react'
import { useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { hhmm, titleCase } from '../../lib/format'
import { Badge, Btn, Empty, PageHeader, Panel, ReasonDialog, useAction } from '../ui'

const KINDS = [
  { value: 'cancellation', label: 'Service cancellation' },
  { value: 'delay', label: 'Service delay' },
  { value: 'route_closure', label: 'Route closure' },
  { value: 'vehicle_unavailable', label: 'Vehicle unavailable' },
  { value: 'capacity_reduction', label: 'Vehicle capacity reduction' },
]

export default function Simulation() {
  const { data: disruptions, refetch } = useLive(opApi, '/op/disruptions')
  const { data: services } = useLive(opApi, '/network/services')
  const { data: vehicles } = useLive(opApi, '/op/vehicles')
  const { data: segments } = useLive(opApi, '/network/segments')
  const { busy, run } = useAction()

  const [kind, setKind] = useState('cancellation')
  const [serviceId, setServiceId] = useState('X5')
  const [vehicleId, setVehicleId] = useState('RV-1')
  const [segmentId, setSegmentId] = useState('')
  const [delay, setDelay] = useState(30)
  const [capacity, setCapacity] = useState(4)
  const [resetting, setResetting] = useState(false)

  const usesService = kind === 'cancellation' || kind === 'delay'
  const usesVehicle = kind === 'vehicle_unavailable' || kind === 'capacity_reduction'
  const open = segments?.filter((s: any) => !s.blocked) ?? []
  const x5Live = disruptions?.some((d: any) => d.status === 'active' && d.kind === 'cancellation' && d.service_id === 'X5')

  const trigger = (body: Record<string, unknown>) =>
    run(() => opApi.post('/op/disruptions', body).then(refetch), 'Disruption applied. Alternatives, groups and allocations reassessed.')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body: Record<string, unknown> = { kind }
    if (usesService) body.service_id = serviceId
    if (usesVehicle) body.vehicle_id = vehicleId
    if (kind === 'route_closure') body.segment_id = Number(segmentId || open[0]?.id)
    if (kind === 'delay') body.delay_min = delay
    if (kind === 'capacity_reduction') body.new_capacity = capacity
    trigger(body)
  }

  return (
    <>
      <PageHeader title="Disruption simulation" sub="Every disruption reruns the same pipeline: identify affected passengers, regenerate alternatives, regroup, and reassess live allocations." />
      <div className="grid gap-3 lg:grid-cols-[360px_1fr]">
        <div className="grid content-start gap-3">
          <Panel title="Demonstration scenario">
            <p className="text-xs text-op-muted">Evening commute: the X5 Cross-City Express is cancelled with 24 passengers in 14 parties. Three replacement vehicles offer 20 seats.</p>
            <div className="mt-3 grid gap-2">
              <Btn variant="primary" className="py-1.5" disabled={busy || x5Live} onClick={() => trigger({ kind: 'cancellation', service_id: 'X5' })}>
                <Play size={13} /> {x5Live ? 'X5 already cancelled' : 'Cancel the X5'}
              </Btn>
              <Btn className="py-1.5" disabled={busy || !x5Live} onClick={() => run(() => opApi.post('/demo/simulate-preferences'), (r) => `${r.simulated} simulated passengers responded`)}>
                <UsersRound size={13} /> Simulate passenger responses
              </Btn>
              <Btn variant="danger" className="py-1.5" disabled={busy} onClick={() => setResetting(true)}>
                <RotateCcw size={13} /> Reset scenario
              </Btn>
            </div>
            <p className="mt-2 text-[11px] text-op-faint">Simulated responses are marked as simulated in the audit log. Two parties stay silent, so you can see non-responders, and any choice already made in the passenger app is kept.</p>
          </Panel>

          <Panel title="Inject a disruption">
            <form onSubmit={submit} className="grid gap-2.5 text-xs">
              <label className="grid gap-1 text-op-muted">Type
                <select className="op-input" value={kind} onChange={(e) => setKind(e.target.value)}>
                  {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>
              </label>
              {usesService && (
                <label className="grid gap-1 text-op-muted">Service
                  <select className="op-input" value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
                    {services?.map((s: any) => <option key={s.id} value={s.id}>{s.name} ({s.status})</option>)}
                  </select>
                </label>
              )}
              {usesVehicle && (
                <label className="grid gap-1 text-op-muted">Vehicle
                  <select className="op-input" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
                    {vehicles?.map((v: any) => <option key={v.id} value={v.id}>{v.id}, {v.capacity} seats ({v.status})</option>)}
                  </select>
                </label>
              )}
              {kind === 'route_closure' && (
                <label className="grid gap-1 text-op-muted">Road segment
                  <select className="op-input" value={segmentId} onChange={(e) => setSegmentId(e.target.value)}>
                    {open.map((s: any) => <option key={s.id} value={s.id}>{s.a_name} – {s.b_name}</option>)}
                  </select>
                </label>
              )}
              {kind === 'delay' && (
                <label className="grid gap-1 text-op-muted">Delay in minutes
                  <input className="op-input" type="number" min={1} max={240} value={delay} onChange={(e) => setDelay(Number(e.target.value))} />
                </label>
              )}
              {kind === 'capacity_reduction' && (
                <label className="grid gap-1 text-op-muted">New capacity
                  <input className="op-input" type="number" min={0} max={50} value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} />
                </label>
              )}
              <Btn type="submit" disabled={busy} className="py-1.5">Apply disruption</Btn>
            </form>
          </Panel>
        </div>

        <Panel title="Disruption log" flush className="self-start">
          {disruptions?.length ? (
            <table className="op-table">
              <thead><tr><th>ID</th><th>Type</th><th>Description</th><th>Start</th><th>Passengers</th><th>Status</th><th /></tr></thead>
              <tbody>
                {disruptions.map((d: any) => (
                  <tr key={d.id}>
                    <td className="num">{d.code}</td>
                    <td className="whitespace-nowrap">{titleCase(d.kind)}</td>
                    <td className="text-op-muted">{d.description}</td>
                    <td className="num">{hhmm(d.start_min)}</td>
                    <td className="num">{d.affected}</td>
                    <td><Badge tone={d.status === 'active' ? 'warn' : 'neutral'}>{titleCase(d.status)}</Badge></td>
                    <td className="text-right">
                      {d.status === 'active' && (
                        <Btn disabled={busy} onClick={() => run(() => opApi.post(`/op/disruptions/${d.id}/resolve`).then(refetch), `${d.code} resolved`)}>Resolve</Btn>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>The network is running normally. No disruptions recorded.</Empty>}
        </Panel>
      </div>

      {resetting && (
        <ReasonDialog
          title="Reset the scenario?"
          body="This deletes all disruptions, allocations, carpools and audit history, and restores the 24-passenger scenario."
          confirmLabel="Reset"
          danger
          noReason
          onCancel={() => setResetting(false)}
          onConfirm={() => {
            setResetting(false)
            run(() => opApi.post('/demo/reset').then(refetch), 'Scenario reset')
          }}
        />
      )}
    </>
  )
}
