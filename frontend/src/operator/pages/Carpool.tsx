import { opApi, useLive } from '../../lib/api'
import { hhmm, titleCase } from '../../lib/format'
import { Badge, Empty, Loading, PageHeader, Panel, Stat, StatRow, type Tone } from '../ui'

const TONE: Record<string, Tone> = {
  open: 'warn', offer_received: 'info', match_proposed: 'info', awaiting_passenger: 'info', awaiting_provider: 'info',
  confirmed: 'good', completed: 'good', cancelled: 'neutral', withdrawn: 'neutral',
}

export default function Carpool() {
  const { data, error } = useLive(opApi, '/op/carpool')
  if (!data) return <Loading error={error} />
  const s = data.summary
  return (
    <>
      <PageHeader
        title="Community carpool monitoring"
        sub="Rides offered by ordinary users, tracked apart from official transport. They never count as allocations and never use vehicle seats. Providers are not verified."
      />
      <StatRow>
        <Stat label="Still need transport" value={s.needing_transport} tone={s.needing_transport ? 'bad' : undefined} />
        <Stat label="Open requests" value={s.open_requests} />
        <Stat label="Offers received" value={s.offers_received} />
        <Stat label="Proposed matches" value={s.proposed_matches} />
        <Stat label="Confirmed arrangements" value={s.confirmed_arrangements} sub={`${s.confirmed_passengers} passengers`} tone={s.confirmed_arrangements ? 'good' : undefined} />
        <Stat label="Unmatched demand" value={s.remaining_unmatched} sub={s.reports ? `${s.reports} reports filed` : 'No reports filed'} />
      </StatRow>

      <div className="mt-3 grid gap-3">
        <Panel title="Aggregated requests" flush>
          {data.requests.length ? (
            <table className="op-table">
              <thead><tr><th>Listing</th><th>Pickup area</th><th>Destination</th><th>Waiting</th><th>Departure window</th><th>Status</th></tr></thead>
              <tbody>
                {data.requests.map((r: any) => (
                  <tr key={r.id}>
                    <td className="num">{r.label}</td>
                    <td>{r.pickup_area}</td>
                    <td>{r.destination}</td>
                    <td className="num">{r.passengers}</td>
                    <td className="num">{hhmm(r.window_start)}–{hhmm(r.window_end)}</td>
                    <td><Badge tone={TONE[r.status]}>{titleCase(r.status)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty>Listings appear after official seats are reserved and demand remains.</Empty>}
        </Panel>

        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Offers" flush>
            {data.offers.length ? (
              <table className="op-table">
                <thead><tr><th>Offer</th><th>Route</th><th>Departs</th><th>Seats</th><th>Status</th></tr></thead>
                <tbody>
                  {data.offers.map((o: any) => (
                    <tr key={o.id}>
                      <td className="num">{o.label}</td>
                      <td>{o.origin} → {o.destination}<span className="block text-[11px] text-op-muted">{o.vehicle_type}</span></td>
                      <td className="num">{hhmm(o.departure)}</td>
                      <td className="num">{o.reserved}/{o.seats}</td>
                      <td><Badge tone={TONE[o.status]}>{titleCase(o.status)}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty>No community offers yet.</Empty>}
          </Panel>
          <Panel title="Matches" flush>
            {data.matches.length ? (
              <table className="op-table">
                <thead><tr><th>Match</th><th>Link</th><th>Seats</th><th>Detour</th><th>Passengers</th><th>Provider</th><th>Status</th></tr></thead>
                <tbody>
                  {data.matches.map((m: any) => (
                    <tr key={m.id}>
                      <td className="num">{m.label}</td>
                      <td className="num whitespace-nowrap text-op-muted">{m.offer} → {m.request}</td>
                      <td className="num">{m.seats}</td>
                      <td className="num">{m.detour_min} min</td>
                      <td className="text-op-muted">{titleCase(m.passenger_acceptance)}</td>
                      <td className="text-op-muted">{titleCase(m.provider_confirmation)}</td>
                      <td><Badge tone={TONE[m.status]}>{titleCase(m.status)}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty>No proposed matches yet.</Empty>}
          </Panel>
        </div>
      </div>
    </>
  )
}
