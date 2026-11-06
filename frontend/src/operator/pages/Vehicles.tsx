import { Plus } from 'lucide-react'
import { useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { hhmm, parseHhmm } from '../../lib/format'
import { Badge, Btn, Loading, PageHeader, Panel, useAction } from '../ui'

function AddVehicle({ stops, onDone }: { stops: any[]; onDone: () => void }) {
  const { busy, run } = useAction()
  const [form, setForm] = useState({ id: 'RV-4', vehicle_type: 'Van', capacity: 6, ready: '18:15', route: 'HEB,KRP,WFD', wheelchair: false })
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))
  return (
    <form
      className="grid gap-2 text-xs sm:grid-cols-[80px_1fr_70px_120px_1.4fr_auto_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        const route = form.route.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean)
        run(() => opApi.post('/op/vehicles', {
          id: form.id, vehicle_type: form.vehicle_type, capacity: form.capacity, stops: route,
          ready_min: parseHhmm(form.ready), wheelchair: form.wheelchair, luggage: true,
        }).then(onDone), `${form.id} added. Alternatives have been regenerated.`)
      }}
    >
      <label className="grid gap-1 text-op-muted">ID<input className="op-input" value={form.id} onChange={(e) => set('id', e.target.value)} /></label>
      <label className="grid gap-1 text-op-muted">Type<input className="op-input" value={form.vehicle_type} onChange={(e) => set('vehicle_type', e.target.value)} /></label>
      <label className="grid gap-1 text-op-muted">Seats<input className="op-input" type="number" min={1} max={100} value={form.capacity} onChange={(e) => set('capacity', Number(e.target.value))} /></label>
      <label className="grid gap-1 text-op-muted">Departs<input className="op-input" type="time" value={form.ready} onChange={(e) => set('ready', e.target.value)} /></label>
      <label className="grid gap-1 text-op-muted">Route (stop codes)<input className="op-input" value={form.route} onChange={(e) => set('route', e.target.value)} title={stops.map((s) => `${s.id} ${s.name}`).join(', ')} /></label>
      <label className="flex items-center gap-1.5 py-1.5 text-op-muted"><input type="checkbox" checked={form.wheelchair} onChange={(e) => set('wheelchair', e.target.checked)} /> Step-free</label>
      <Btn type="submit" disabled={busy} className="py-1.5"><Plus size={12} /> Add</Btn>
    </form>
  )
}

export default function Vehicles() {
  const { data, error, refetch } = useLive(opApi, '/op/vehicles')
  const { data: stops } = useLive(opApi, '/network/stops')
  const { busy, run } = useAction()
  if (!data) return <Loading error={error} />

  const total = data.reduce((n: number, v: any) => n + (v.status === 'available' ? v.capacity : 0), 0)
  const free = data.reduce((n: number, v: any) => n + (v.status === 'available' ? v.available_seats : 0), 0)

  return (
    <>
      <PageHeader title="Vehicle management" sub={`${free} of ${total} official seats free. Seat counts change only through atomic reservations in the database.`} />
      <div className="grid gap-3 lg:grid-cols-3">
        {data.map((v: any) => (
          <Panel
            key={v.id}
            title={<span><span className="num">{v.id}</span> <span className="font-normal text-op-muted">{v.vehicle_type}</span></span>}
            action={
              v.route_blocked ? <Badge tone="bad">Route cut</Badge>
                : <Badge tone={v.status === 'available' ? 'good' : 'bad'}>{v.status === 'available' ? 'In service' : 'Unavailable'}</Badge>
            }
          >
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-op-muted">Seats remaining</span>
              <span className="num text-lg">{v.available_seats}<span className="text-op-muted">/{v.capacity}</span></span>
            </div>
            <div className="mt-1 flex gap-0.5">
              {Array.from({ length: v.capacity }, (_, i) => (
                <span key={i} className={`h-3 flex-1 rounded-[1px] ${i < v.booked ? 'bg-op-good' : 'bg-op-raised'}`} />
              ))}
            </div>
            <p className="mt-2 text-[11px] text-op-muted">{[v.wheelchair ? 'Step-free, wheelchair lift' : 'Not step-free', v.luggage ? 'Luggage space' : 'No luggage space'].join(' · ')}</p>

            <h3 className="mt-3 text-[11px] text-op-muted">Run</h3>
            <ol className="mt-1 border-l border-op-line-strong pl-3">
              {v.calls.map((c: any) => (
                <li key={c.stop} className="flex justify-between gap-2 py-0.5 text-xs"><span>{c.stop}</span><span className="num text-op-muted">{hhmm(c.time)}</span></li>
              ))}
            </ol>

            <h3 className="mt-3 text-[11px] text-op-muted">Manifest</h3>
            {v.manifest.length ? (
              <ul className="mt-1">
                {v.manifest.map((m: any) => (
                  <li key={m.ref} className="flex justify-between gap-2 py-0.5 text-xs">
                    <span><span className="num">{m.ref}</span> <span className="text-op-muted">×{m.seats}</span></span>
                    <span className="text-op-muted">{m.pickup}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="mt-1 text-xs text-op-faint">No seats reserved.</p>}

            <div className="mt-3 border-t border-op-line pt-3">
              <Btn
                variant={v.status === 'available' ? 'danger' : 'default'}
                disabled={busy}
                onClick={() => {
                  const status = v.status === 'available' ? 'unavailable' : 'available'
                  run(() => opApi.patch(`/op/vehicles/${v.id}`, { status }).then(refetch), `${v.id} marked ${status}`)
                }}
              >
                {v.status === 'available' ? 'Withdraw from service' : 'Return to service'}
              </Btn>
            </div>
          </Panel>
        ))}
      </div>
      <Panel title="Add replacement vehicle" className="mt-3">
        <AddVehicle stops={stops ?? []} onDone={refetch} />
      </Panel>
    </>
  )
}
