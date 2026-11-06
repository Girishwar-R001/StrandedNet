import { Play, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { opApi, useLive } from '../../lib/api'
import { hhmm } from '../../lib/format'
import { Badge, Btn, Empty, Loading, PageHeader, Panel, ReasonDialog, Stat, StatRow, StateBadge, useAction, type Tone } from '../ui'

export const PREF_OUTCOME: Record<string, [string, Tone]> = {
  first_choice: ['First choice', 'good'],
  second_choice: ['Second choice', 'info'],
  other_feasible: ['Not ranked', 'warn'],
  no_preference: ['No preference', 'neutral'],
}

const WEIGHT_LABEL: Record<string, string> = {
  waiting: 'Waiting time',
  urgency: 'Arrival urgency',
  scarcity: 'Lack of alternatives',
  group: 'Party integrity',
  preference: 'Passenger preference',
}

function Rules() {
  const { data, refetch } = useLive(opApi, '/op/rules')
  const [weights, setWeights] = useState<Record<string, number> | null>(null)
  const [saving, setSaving] = useState(false)
  const { run } = useAction()
  useEffect(() => {
    if (data) setWeights(data.weights)
  }, [data])
  if (!data || !weights) return null
  const sum = Object.values(weights).reduce((a, b) => a + b, 0)
  const dirty = JSON.stringify(weights) !== JSON.stringify(data.weights)
  const valid = Math.abs(sum - 1) < 0.001
  return (
    <Panel title="Prioritisation rules">
      <p className="num text-[11px] text-op-muted">{data.formula}</p>
      <div className="mt-3 grid gap-2.5">
        {Object.keys(WEIGHT_LABEL).map((k) => (
          <label key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-2 text-xs">
            <span className="text-op-muted">{WEIGHT_LABEL[k]}</span>
            <span className="num">{weights[k].toFixed(2)}</span>
            <input
              type="range" min={0} max={1} step={0.05} value={weights[k]} className="col-span-2 accent-[#f0b429]"
              onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })}
            />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 text-xs">
        <span className={valid ? 'text-op-muted' : 'text-op-bad'}>Total <span className="num">{sum.toFixed(2)}</span>{valid ? '' : ', must equal 1.00'}</span>
        <Btn disabled={!dirty || !valid} onClick={() => setSaving(true)}>Save weights</Btn>
      </div>
      <h3 className="mt-3 border-t border-op-line pt-3 text-[11px] text-op-muted">Hard constraints (never scored, never overridden by weights)</h3>
      <ul className="mt-1 grid gap-0.5 text-xs">
        {data.constraints.map((c: string) => <li key={c} className="flex gap-1.5"><ShieldCheck size={12} className="mt-0.5 shrink-0 text-op-good" />{c}</li>)}
      </ul>
      {saving && (
        <ReasonDialog
          title="Change prioritisation weights"
          body="Takes effect from the next engine run."
          confirmLabel="Save"
          onCancel={() => setSaving(false)}
          onConfirm={(reason) => {
            setSaving(false)
            run(() => opApi.put('/op/rules', { weights, reason }).then(refetch), 'Weights updated')
          }}
        />
      )}
    </Panel>
  )
}

export default function Allocation() {
  const { data, error, refetch } = useLive(opApi, '/op/allocations')
  const { data: latest, refetch: refetchRun } = useLive(opApi, '/op/allocation/latest')
  const { data: vehicles } = useLive(opApi, '/op/vehicles')
  const { busy, run } = useAction()
  const [rejecting, setRejecting] = useState<any>(null)
  if (!data) return <Loading error={error} />

  const pending = data.filter((a: any) => a.status === 'proposed' || a.status === 'approved')
  const refresh = () => Promise.all([refetch(), refetchRun()])
  const s = latest?.summary

  return (
    <>
      <PageHeader
        title="Smart allocation"
        sub="The engine only proposes. A seat exists once its reservation commits in the database, after a final capacity recheck."
        action={
          <>
            <Btn disabled={busy} onClick={() => run(() => opApi.post('/op/allocation/run').then(refresh), 'Engine run complete')}><Play size={12} /> Run engine</Btn>
            <Btn
              variant="primary" disabled={busy || !pending.length}
              onClick={() => run(() => opApi.post('/op/allocations/confirm-all').then(async (r) => { await refresh(); return r }),
                (r) => `${r.confirmed} reserved${r.failed.length ? `, ${r.failed.length} failed` : ''}. Unmet demand published to carpool.`)}
            >
              Approve and reserve all ({pending.length})
            </Btn>
          </>
        }
      />

      {s && (
        <StatRow cols={5}>
          <Stat label="Solver" value={<span className="text-base">{latest.solver === 'cp_sat' ? 'OR-Tools CP-SAT' : 'Greedy'}</span>} sub={`Run ${latest.run_id}`} />
          <Stat label="Demand considered" value={s.demand_seats} sub={`${s.candidates} parties`} />
          <Stat label="Seats proposed" value={s.engine.seats} sub={`of ${s.supply_seats} available`} />
          <Stat label="Parties not placed" value={s.unplaced.length} sub="See reasons below" tone={s.unplaced.length ? 'warn' : undefined} />
          <Stat label="Stranded, no alternative" value={s.engine.stranded_no_alternative} sub={`First come: ${s.baseline_fcfs.stranded_no_alternative}`} tone={s.engine.stranded_no_alternative < s.baseline_fcfs.stranded_no_alternative ? 'good' : undefined} />
        </StatRow>
      )}

      <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_290px]">
        <div className="grid min-w-0 content-start gap-3">
          <Panel title="Allocations" flush action={<Link to="/operator/explanations" className="text-xs text-op-muted hover:text-op-text">Inspect explanations</Link>}>
            {data.length ? (
              <table className="op-table">
                <thead><tr><th>Party</th><th>Seats</th><th>Vehicle</th><th>Pickup</th><th>Arrive</th><th>Priority</th><th>Preference</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {data.map((a: any) => {
                    const [label, tone] = PREF_OUTCOME[a.preference_outcome]
                    return (
                      <tr key={a.id}>
                        <td className="num">{a.ref}</td>
                        <td className="num">{a.party_size}</td>
                        <td className="num">{a.vehicle_id}</td>
                        <td className="whitespace-nowrap">{a.pickup_stop} <span className="num text-op-muted">{hhmm(a.pickup_min)}</span></td>
                        <td className="num">{hhmm(a.arrival_min)}</td>
                        <td className="num">{a.is_override ? <span className="text-op-signal">Override</span> : a.priority_score.toFixed(2)}</td>
                        <td><Badge tone={tone}>{label}</Badge></td>
                        <td><StateBadge state={a.status} /></td>
                        <td>
                          <div className="flex justify-end gap-1">
                            {a.status === 'proposed' && <Btn disabled={busy} onClick={() => run(() => opApi.post(`/op/allocations/${a.id}/approve`).then(refresh), `${a.ref} approved`)}>Approve</Btn>}
                            {(a.status === 'proposed' || a.status === 'approved') && <Btn disabled={busy} onClick={() => run(() => opApi.post(`/op/allocations/${a.id}/confirm`).then(refresh), `Seats reserved for ${a.ref}`)}>Reserve</Btn>}
                            {a.status !== 'needs_review' && <Btn variant="ghost" disabled={busy} onClick={() => setRejecting(a)}>{a.status === 'confirmed' ? 'Release' : 'Reject'}</Btn>}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : <Empty>No allocations yet. Run the engine once passengers are affected.</Empty>}
          </Panel>

          {s?.unplaced.length > 0 && (
            <Panel title="Not placed in the latest run" flush>
              <table className="op-table">
                <thead><tr><th>Party</th><th>Seats</th><th>Reason</th></tr></thead>
                <tbody>
                  {s.unplaced.map((u: any) => (
                    <tr key={u.ref}><td className="num">{u.ref}</td><td className="num">{u.party_size}</td><td className="text-op-muted">{u.reason}</td></tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>

        <div className="grid content-start gap-3">
          <Panel title="Remaining capacity">
            <ul className="grid gap-1.5 text-xs">
              {vehicles?.map((v: any) => (
                <li key={v.id} className="flex justify-between"><span className="num">{v.id}</span><span className="num text-op-muted">{v.available_seats} of {v.capacity} free</span></li>
              ))}
            </ul>
          </Panel>
          <Rules />
        </div>
      </div>

      {rejecting && (
        <ReasonDialog
          title={`${rejecting.status === 'confirmed' ? 'Release' : 'Reject'} ${rejecting.ref} on ${rejecting.vehicle_id}`}
          confirmLabel="Confirm"
          danger
          onCancel={() => setRejecting(null)}
          onConfirm={(reason) => {
            const id = rejecting.id
            setRejecting(null)
            run(() => opApi.post(`/op/allocations/${id}/reject`, { reason }).then(refresh), 'Allocation cancelled and capacity returned')
          }}
        />
      )}
    </>
  )
}
