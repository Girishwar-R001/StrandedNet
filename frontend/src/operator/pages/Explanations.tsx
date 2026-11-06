import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { Badge, Empty, Loading, PageHeader, Panel, StateBadge } from '../ui'
import { PREF_OUTCOME } from './Allocation'

const COLORS: Record<string, string> = {
  waiting: '#006194', urgency: '#d97706', scarcity: '#00855d', group: '#7c5cbf', preference: '#2f9f9f',
}

function Detail({ a }: { a: any }) {
  const factors = a.breakdown?.factors
  const [label, tone] = PREF_OUTCOME[a.preference_outcome]
  return (
    <div className="grid gap-4">
      <div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="num text-sm">{a.ref} → {a.vehicle_id}</span>
          <StateBadge state={a.status} />
          <Badge tone={tone}>{label}</Badge>
          {a.is_override && <Badge tone="warn">Operator override</Badge>}
        </div>
        <p className="mt-2 max-w-2xl text-[13px]">{a.explanation}</p>
        {a.override_reason && <p className="mt-1 text-xs text-op-signal">Override reason: {a.override_reason}</p>}
        {a.flag_reason && <p className="mt-1 text-xs text-op-muted">Note: {a.flag_reason}</p>}
      </div>

      {factors && (
        <div>
          <div className="flex items-baseline justify-between">
            <h3 className="text-[11px] text-op-muted">Priority score breakdown</h3>
            <span className="num text-lg">{a.priority_score.toFixed(2)}</span>
          </div>
          <div className="mt-1 flex h-2.5 gap-px overflow-hidden rounded-sm bg-op-raised">
            {Object.entries<any>(factors).map(([k, f]) => <div key={k} style={{ width: `${f.points * 100}%`, background: COLORS[k] }} title={f.label} />)}
          </div>
          <table className="op-table mt-2">
            <thead><tr><th>Factor</th><th className="text-right!">Value</th><th className="text-right!">Weight</th><th className="text-right!">Points</th></tr></thead>
            <tbody>
              {Object.entries<any>(factors).map(([k, f]) => (
                <tr key={k}>
                  <td><span className="mr-1.5 inline-block size-2 rounded-sm" style={{ background: COLORS[k] }} />{f.label}</td>
                  <td className="num text-right text-op-muted">{f.value.toFixed(2)}</td>
                  <td className="num text-right text-op-muted">{f.weight.toFixed(2)}</td>
                  <td className="num text-right">{f.points.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="num mt-2 text-[11px] text-op-muted">
            waited {a.breakdown.inputs.waited_min} min · slack {a.breakdown.inputs.slack_min} min · {a.breakdown.inputs.walkup_alternatives} walk-up alternatives · party of {a.breakdown.inputs.party_size}
          </p>
        </div>
      )}

      <div>
        <h3 className="text-[11px] text-op-muted">Feasibility checks at last evaluation</h3>
        <ul className="mt-1 grid gap-0.5">
          {a.checks.map((c: any) => (
            <li key={c.name} className="flex gap-1.5 text-xs">
              {c.ok ? <Check size={13} className="mt-px shrink-0 text-op-good" /> : <X size={13} className="mt-px shrink-0 text-op-bad" />}
              {c.detail}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function Explanations() {
  const { data, error } = useLive(opApi, '/op/allocations?include_closed=true')
  const [selected, setSelected] = useState<number | null>(null)
  if (!data) return <Loading error={error} />
  const picked = data.find((a: any) => a.id === selected) ?? data[0]
  return (
    <>
      <PageHeader title="Allocation explanations" sub="Every decision shows its score, the arithmetic behind it, and the feasibility checks it passed. Superseded and released decisions are kept." />
      {data.length === 0 ? <Panel><Empty>No decisions yet. Run the allocation engine first.</Empty></Panel> : (
        <div className="grid gap-3 lg:grid-cols-[340px_1fr]">
          <Panel flush className="max-h-[calc(100vh-150px)] overflow-y-auto">
            <table className="op-table">
              <thead><tr><th>Party</th><th>Vehicle</th><th>Score</th><th>Status</th></tr></thead>
              <tbody>
                {data.map((a: any) => (
                  <tr key={a.id} className="row-link" onClick={() => setSelected(a.id)}>
                    <td className={`num ${picked?.id === a.id ? 'font-semibold text-op-primary' : ''}`}>{a.ref}</td>
                    <td className="num">{a.vehicle_id}</td>
                    <td className="num">{a.is_override ? '–' : a.priority_score.toFixed(2)}</td>
                    <td><StateBadge state={a.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          {picked && <Panel className="self-start"><Detail a={picked} /></Panel>}
        </div>
      )}
    </>
  )
}
