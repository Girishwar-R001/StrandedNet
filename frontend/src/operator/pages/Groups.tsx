import { RefreshCw } from 'lucide-react'
import { opApi, useLive } from '../../lib/api'
import { hhmm, plural, REQUIREMENT_LABEL } from '../../lib/format'
import { Btn, Empty, Loading, PageHeader, Panel, useAction } from '../ui'

const PARTS: [string, string][] = [['route', 'Route'], ['time', 'Time'], ['pickup', 'Pickup'], ['destination', 'Destination'], ['requirements', 'Needs']]

export default function Groups() {
  const { data, error, refetch } = useLive(opApi, '/op/groups')
  const { busy, run } = useAction()
  if (!data) return <Loading error={error} />
  return (
    <>
      <PageHeader
        title="Passenger grouping"
        sub="Complete-linkage clustering on directed route overlap, departure windows, pickup distance and requirements. Sharing a destination name is never enough."
        action={<Btn disabled={busy} onClick={() => run(() => opApi.post('/op/groups/run').then(refetch), 'Groups refreshed')}><RefreshCw size={12} /> Refresh grouping</Btn>}
      />
      {data.length === 0 ? <Panel><Empty>No waiting passengers to group.</Empty></Panel> : (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.map((g: any) => (
            <Panel
              key={g.id}
              title={<span className="num">{g.label}</span>}
              action={<span className="text-xs text-op-muted">Compatibility <span className="num text-op-text">{g.score.toFixed(2)}</span></span>}
            >
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
                {[
                  ['Passengers', `${g.passengers} in ${plural(g.parties, 'party', 'parties')}`],
                  ['Destination zone', g.destination_zone],
                  ['Pickup point', g.pickup_point],
                  ['Est. journey', `${g.est_minutes} min`],
                ].map(([k, v]) => (
                  <div key={k}><dt className="text-[11px] text-op-muted">{k}</dt><dd className="mt-0.5">{v}</dd></div>
                ))}
              </dl>
              {g.parties > 1 && (
                <div className="mt-3 grid grid-cols-5 gap-2">
                  {PARTS.map(([key, label]) => (
                    <div key={key}>
                      <div className="flex justify-between text-[10px] text-op-muted"><span>{label}</span><span className="num">{Math.round((g.breakdown[key] ?? 0) * 100)}</span></div>
                      <div className="mt-0.5 h-1 rounded-sm bg-op-raised"><div className="h-full rounded-sm bg-op-info" style={{ width: `${(g.breakdown[key] ?? 0) * 100}%` }} /></div>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-3 text-xs text-op-muted">{g.explanation}</p>
              <ul className="mt-2 border-t border-op-line pt-2">
                {g.members.map((m: any) => (
                  <li key={m.ref} className="flex flex-wrap items-baseline gap-x-3 py-0.5 text-xs">
                    <span className="num">{m.ref}</span>
                    <span className="text-op-muted">×{m.party_size}</span>
                    <span>{m.origin} → {m.destination}</span>
                    <span className="num text-op-muted">{hhmm(m.dep_earliest)}–{hhmm(m.dep_latest)}</span>
                    {m.requirements.map((r: string) => <span key={r} className="text-op-signal">{REQUIREMENT_LABEL[r]}</span>)}
                  </li>
                ))}
              </ul>
            </Panel>
          ))}
        </div>
      )}
    </>
  )
}
