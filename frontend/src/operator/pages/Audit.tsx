import { useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { titleCase } from '../../lib/format'
import { Empty, Loading, PageHeader, Panel } from '../ui'

export default function Audit() {
  const [type, setType] = useState('')
  const [query, setQuery] = useState('')
  const params = new URLSearchParams({ limit: '500' })
  if (type) params.set('event_type', type)
  if (query) params.set('q', query)
  const { data, error } = useLive(opApi, `/op/audit?${params}`)
  if (!data) return <Loading error={error} />
  return (
    <>
      <PageHeader
        title="Audit log"
        sub={`${data.events.length} events. Append-only: every decision, confirmation, change and override, with its reason and actor.`}
        action={
          <>
            <input className="op-input w-44" placeholder="Search" aria-label="Search audit log" value={query} onChange={(e) => setQuery(e.target.value)} />
            <select className="op-input" aria-label="Filter by event type" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All events</option>
              {data.types.map((t: string) => <option key={t} value={t}>{titleCase(t)}</option>)}
            </select>
          </>
        }
      />
      <Panel flush>
        {data.events.length ? (
          <table className="op-table">
            <thead><tr><th>Time (UTC)</th><th>Event</th><th>Entity</th><th>Decision or change</th><th>Reason</th><th>Actor</th></tr></thead>
            <tbody>
              {data.events.map((e: any) => (
                <tr key={e.id}>
                  <td className="num whitespace-nowrap text-op-muted">{e.timestamp.slice(11, 19)}</td>
                  <td className="whitespace-nowrap">{titleCase(e.event_type)}</td>
                  <td className="num whitespace-nowrap text-op-muted">{e.entity}</td>
                  <td>{e.change}</td>
                  <td className="max-w-md text-op-muted">{e.reason || '–'}</td>
                  <td className="whitespace-nowrap text-op-muted">{e.actor.replace('@stranded.demo', '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>No events match.</Empty>}
      </Panel>
    </>
  )
}
