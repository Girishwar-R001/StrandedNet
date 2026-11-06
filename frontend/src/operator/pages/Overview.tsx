import { Check, Circle, CircleDot } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { opApi, useLive } from '../../lib/api'
import { Empty, Loading, PageHeader, Panel, Stat, StatRow } from '../ui'

const SEGMENTS = [
  { key: 'official_confirmed', label: 'Seat confirmed', color: 'var(--color-op-good)' },
  { key: 'carpool_confirmed', label: 'Carpool confirmed', color: '#35a58a' },
  { key: 'approved', label: 'Approved', color: 'var(--color-op-info)' },
  { key: 'proposed', label: 'Proposed', color: '#7fb3e0' },
  { key: 'needs_review', label: 'Needs review', color: 'var(--color-op-signal)' },
  { key: 'self_resolved', label: 'Self-resolved', color: 'var(--color-op-faint)' },
  { key: 'unresolved', label: 'Unresolved', color: 'var(--color-op-bad)' },
]

function RecoveryBar({ byState, total }: { byState: Record<string, number>; total: number }) {
  const present = SEGMENTS.filter((s) => byState[s.key])
  return (
    <div>
      <div className="flex h-3 gap-px overflow-hidden rounded-sm bg-op-raised">
        {present.map((s) => (
          <div key={s.key} style={{ width: `${(100 * byState[s.key]) / total}%`, background: s.color }} title={`${s.label}: ${byState[s.key]}`} />
        ))}
      </div>
      <dl className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1">
        {present.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5 text-xs">
            <span className="size-2 rounded-sm" style={{ background: s.color }} />
            <dt className="text-op-muted">{s.label}</dt>
            <dd className="num">{byState[s.key]}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function Comparison({ metrics }: { metrics: any }) {
  const e = metrics.engine
  const b = metrics.baseline
  if (!e || !b) return <Empty>Run allocation to compare the engine with a first-come baseline.</Empty>
  const rows: [string, number, number, boolean][] = [
    ['Seats filled', e.seats, b.seats, true],
    ['Left with no in-time alternative', e.stranded_no_alternative, b.stranded_no_alternative, false],
    ['Parties seated', e.parties, b.parties, true],
    ['First choices honoured', e.first_choice, b.first_choice, true],
    ['Priority-weighted value', e.priority_value, b.priority_value, true],
  ]
  return (
    <table className="op-table">
      <thead>
        <tr><th>Latest run, same feasibility rules</th><th className="text-right!">Engine</th><th className="text-right!">First come</th></tr>
      </thead>
      <tbody>
        {rows.map(([label, engine, base, higher]) => {
          const better = higher ? engine > base : engine < base
          const worse = higher ? engine < base : engine > base
          return (
            <tr key={label}>
              <td className="text-op-muted">{label}</td>
              <td className={`num text-right ${better ? 'text-op-good' : worse ? 'text-op-signal' : ''}`}>{engine}</td>
              <td className="num text-right text-op-muted">{base}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function Overview() {
  const { data, error } = useLive(opApi, '/op/overview')
  const { data: steps } = useLive(opApi, '/demo/progress')
  if (!data) return <Loading error={error} />
  const m = data.metrics
  const s = data.by_state
  const unresolved = (s.unresolved ?? 0) + (s.needs_review ?? 0)

  return (
    <>
      <PageHeader title="Overview" sub="Live recovery position across every active disruption." />
      <StatRow>
        <Stat label="Affected passengers" value={data.affected} sub={`${data.parties} parties`} />
        <Stat label="Official seats confirmed" value={s.official_confirmed ?? 0} sub={m.pct_official !== null ? `${m.pct_official}% of affected` : 'None yet'} tone={s.official_confirmed ? 'good' : undefined} />
        <Stat label="Carpool confirmed" value={s.carpool_confirmed ?? 0} sub="Community rides, not official" />
        <Stat label="Unresolved" value={unresolved} sub={data.needs_review ? `${data.needs_review} need review` : 'Still need transport'} tone={unresolved ? 'bad' : undefined} />
        <Stat label="Seats available" value={`${data.capacity.available}/${data.capacity.total}`} sub="Official replacement" />
        <Stat label="Over-allocations" value={m.over_allocation_count} sub="Independently reconciled" tone={m.over_allocation_count ? 'bad' : 'good'} />
      </StatRow>

      <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_320px]">
        <div className="grid min-w-0 content-start gap-3">
          <Panel title="Recovery progress">
            {data.affected ? <RecoveryBar byState={s} total={data.affected} /> : <Empty>No passengers are affected. Trigger a disruption to begin.</Empty>}
          </Panel>

          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Demand by destination">
              {data.by_destination.length ? (
                <ResponsiveContainer width="100%" height={Math.max(150, data.by_destination.length * 28)}>
                  <BarChart data={data.by_destination} layout="vertical" margin={{ left: 0, right: 12, top: 0, bottom: 0 }}>
                    <XAxis type="number" hide allowDecimals={false} />
                    <YAxis dataKey="name" type="category" width={132} tickLine={false} axisLine={false} tick={{ fill: '#3f4850', fontSize: 11 }} />
                    <Tooltip cursor={{ fill: '#eff4ff' }} contentStyle={{ background: '#fff', border: '1px solid #dbe3f0', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#0d1c2f' }} itemStyle={{ color: '#0d1c2f' }} />
                    <Bar dataKey="passengers" name="Passengers" fill="#006194" barSize={12} radius={[0, 2, 2, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <Empty>No demand yet.</Empty>}
            </Panel>

            <Panel title="Replacement capacity">
              <ul className="grid gap-3">
                {data.vehicles.map((v: any) => {
                  const used = v.capacity - v.available
                  return (
                    <li key={v.id}>
                      <div className="flex items-baseline justify-between gap-2 text-xs">
                        <span><span className="num">{v.id}</span> <span className="text-op-muted">{v.type}</span></span>
                        {v.status === 'available'
                          ? <span className="num text-op-muted">{used}/{v.capacity}</span>
                          : <span className="text-op-bad">Unavailable</span>}
                      </div>
                      <div className="mt-1 flex gap-0.5">
                        {Array.from({ length: v.capacity }, (_, i) => (
                          <span key={i} className={`h-2 flex-1 rounded-sm ${i < used ? 'bg-op-good' : 'bg-op-raised'}`} />
                        ))}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </Panel>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Engine against baseline" flush><Comparison metrics={m} /></Panel>
            <Panel title="Success metrics" flush>
              <table className="op-table">
                <tbody>
                  {[
                    ['Official seat utilisation', m.official_seat_utilisation, '%'],
                    ['Unmet demand met by carpool', m.pct_unmet_via_carpool, '%'],
                    ['Carpool seat utilisation', m.carpool_seat_utilisation, '%'],
                    ['Preferences satisfied', m.pct_preference_satisfied, '%'],
                    ['Decisions with an explanation', m.pct_decisions_explained, '%'],
                    ['Average added journey time', m.avg_additional_minutes, ' min'],
                    ['Disruption to confirmed seat (demo time)', m.avg_seconds_to_confirmation, ' s'],
                    ['Parties with no feasible option', m.parties_no_feasible_option, ''],
                    ['Preferences collected without a call', m.preferences_collected, ''],
                  ].map(([label, value, unit]) => (
                    <tr key={label as string}>
                      <td className="text-op-muted">{label}</td>
                      <td className="num text-right">{value === null ? '–' : `${value}${unit}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>
        </div>

        {steps && (
          <Panel title="Demonstration guide" className="self-start">
            <ol className="grid gap-px">
              {steps.map((step: any, i: number) => (
                <li key={step.title}>
                  <Link to={step.link} className={`flex items-start gap-2 rounded-lg px-1.5 py-1 hover:bg-op-raised ${step.state === 'next' ? 'bg-op-raised' : ''}`}>
                    <span className="mt-0.5 shrink-0">
                      {step.state === 'done' ? <Check size={13} className="text-op-good" />
                        : step.state === 'next' ? <CircleDot size={13} className="text-op-signal" />
                        : <Circle size={13} className="text-op-faint" />}
                    </span>
                    <span className="min-w-0">
                      <span className={`block text-xs ${step.state === 'todo' ? 'text-op-muted' : ''}`}>{i + 1}. {step.title}</span>
                      <span className="block text-[11px] text-op-faint">{step.actor}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          </Panel>
        )}
      </div>
    </>
  )
}
