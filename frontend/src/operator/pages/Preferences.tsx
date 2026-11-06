import { useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { Badge, Empty, Loading, PageHeader, Panel, Stat, StatRow, StateBadge, type Tone } from '../ui'

const STATE_TONE: Record<string, Tone> = {
  first_available: 'good',
  second_feasible: 'info',
  none_feasible: 'bad',
  none_submitted: 'neutral',
}

const AVAIL_TONE: Record<string, string> = {
  available: 'text-op-good',
  walk_up: 'text-op-muted',
  full: 'text-op-signal',
  unavailable: 'text-op-bad',
}

function Choice({ item }: { item: any }) {
  if (!item) return <span className="text-op-faint">–</span>
  return (
    <div className="min-w-40">
      <p className={item.status === 'invalidated' ? 'text-op-muted line-through' : ''}>{item.title}</p>
      <p className={`text-[11px] ${AVAIL_TONE[item.availability.code]}`}>{item.availability.label}</p>
    </div>
  )
}

export default function Preferences() {
  const { data, error } = useLive(opApi, '/op/preferences')
  const [onlyMissing, setOnlyMissing] = useState(false)
  if (!data) return <Loading error={error} />
  const rows = onlyMissing ? data.rows.filter((r: any) => !r.first) : data.rows
  const max = Math.max(1, ...data.options.map((o: any) => o.passengers))

  return (
    <>
      <PageHeader title="Passenger preferences" sub="Ranked by passengers in their own app, with no phone calls. A preference guides the engine but never reserves a seat, and never overrides capacity or feasibility." />
      <StatRow cols={4}>
        <Stat label="Parties responded" value={`${data.submitted}/${data.total}`} />
        <Stat label="No preference yet" value={data.not_selected} tone={data.not_selected ? 'warn' : undefined} />
        <Stat label="First choice available" value={data.rows.filter((r: any) => r.state === 'first_available').length} />
        <Stat label="No chosen option feasible" value={data.rows.filter((r: any) => r.state === 'none_feasible').length} />
      </StatRow>

      <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_340px]">
        <Panel
          title="By party" flush
          action={
            <label className="flex items-center gap-1.5 text-xs text-op-muted">
              <input type="checkbox" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} /> Not selected only
            </label>
          }
        >
          {rows.length ? (
            <table className="op-table">
              <thead><tr><th>Party</th><th>Size</th><th>First choice</th><th>Second choice</th><th>Assessment</th><th>Recovery</th></tr></thead>
              <tbody>
                {rows.map((r: any) => (
                  <tr key={r.ref}>
                    <td className="num">{r.ref}</td>
                    <td className="num">{r.party_size}</td>
                    <td><Choice item={r.first} /></td>
                    <td><Choice item={r.second} /></td>
                    <td><Badge tone={STATE_TONE[r.state]}>{r.state_label}</Badge></td>
                    <td><StateBadge state={r.recovery} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>{onlyMissing ? 'Every party has responded.' : 'No affected passengers yet.'}</Empty>}
        </Panel>

        <Panel title="Demand by option" className="self-start">
          {data.options.length ? (
            <ul className="grid gap-2.5">
              {data.options.map((o: any) => (
                <li key={o.label}>
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="min-w-0 truncate">{o.label}</span>
                    <span className="num shrink-0">{o.passengers}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-[1px] bg-op-raised">
                    <div className={`h-full rounded-[1px] ${o.reservable ? 'bg-op-info' : 'bg-op-faint'}`} style={{ width: `${(100 * o.passengers) / max}%` }} />
                  </div>
                  <p className="mt-0.5 text-[11px] text-op-muted">{o.first} first, {o.second} second · {o.availability}</p>
                </li>
              ))}
            </ul>
          ) : <Empty>Choices will appear here the moment passengers submit them.</Empty>}
          <p className="mt-3 text-[11px] text-op-faint">Bars count passengers whose first choice this is.</p>
        </Panel>
      </div>
    </>
  )
}
