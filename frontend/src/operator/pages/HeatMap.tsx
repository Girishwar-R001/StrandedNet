import { ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { hhmm } from '../../lib/format'
import { heatLayer, L, useMap } from '../../lib/leaflet'
import { Empty, PageHeader, Panel, Stat, StatRow } from '../ui'

const GRADIENT = { 0.2: '#3a5ea8', 0.45: '#3fa7a0', 0.65: '#e9c13c', 0.85: '#ee7a31', 1: '#e23c3c' }
const SCALE_CSS = 'linear-gradient(90deg,#3a5ea8,#3fa7a0,#e9c13c,#ee7a31,#e23c3c)'
const TIMES = [1050, 1080, 1110, 1140, 1170, 1200]

export default function HeatMap() {
  const { ref, map } = useMap(11)
  const [layer, setLayer] = useState('origin')
  const [status, setStatus] = useState('all')
  const [destination, setDestination] = useState('')
  const [disruption, setDisruption] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [showCapacity, setShowCapacity] = useState(true)
  const [cellId, setCellId] = useState<string | null>(null)
  const [zoneName, setZoneName] = useState<string | null>(null)

  const params = new URLSearchParams({ layer, status })
  if (destination) params.set('destination', destination)
  if (disruption) params.set('disruption_id', disruption)
  if (from) params.set('dep_from', from)
  if (to) params.set('dep_to', to)
  const { data, error } = useLive(opApi, `/op/heatmap?${params}`)
  const { data: stops } = useLive(opApi, '/network/stops')
  const { data: disruptions } = useLive(opApi, '/op/disruptions')
  const fitted = useRef(false)

  const zoneCentres = useMemo(() => {
    const out: Record<string, [number, number]> = {}
    const zones: Record<string, any[]> = {}
    for (const s of stops ?? []) (zones[s.zone] ??= []).push(s)
    for (const [z, list] of Object.entries(zones)) {
      out[z] = [list.reduce((n, s) => n + s.lat, 0) / list.length, list.reduce((n, s) => n + s.lng, 0) / list.length]
    }
    return out
  }, [stops])

  useEffect(() => {
    if (!map || !data || !stops) return
    const group = L.layerGroup().addTo(map)
    const byId = Object.fromEntries(stops.map((s: any) => [s.id, s]))

    const max = Math.max(1, data.max_intensity)
    heatLayer(data.cells.map((c: any) => [c.lat, c.lng, c.affected / max]), {
      radius: 42, blur: 30, max: 1, minOpacity: 0.3, gradient: GRADIENT,
    }).addTo(group)

    for (const c of data.cells) {
      const half = c.size_deg / 2
      const rect = L.rectangle([[c.lat - half, c.lng - half], [c.lat + half, c.lng + half]], {
        color: c.unresolved ? '#ff8a80' : '#e4e6e9', weight: c.id === cellId ? 2 : 0.75,
        opacity: c.id === cellId ? 1 : 0.55, fillOpacity: 0,
      }).addTo(group)
      rect.on('click', () => {
        setCellId(c.id)
        setZoneName(null)
      })
      rect.bindTooltip(`${c.affected} affected · ${c.unresolved} unresolved`, { sticky: true })
    }

    // Disruption-affected zones: every disrupted service corridor and closed road.
    for (const svc of data.disrupted_services) {
      for (const branch of svc.branches) {
        const pts = branch.map((id: string) => [byId[id].lat, byId[id].lng] as [number, number])
        L.polyline(pts, { color: '#f0b429', weight: 1.5, dashArray: '6 6', opacity: 0.75, interactive: false }).addTo(group)
      }
    }
    for (const seg of data.closed_segments) {
      L.polyline([[byId[seg.from].lat, byId[seg.from].lng], [byId[seg.to].lat, byId[seg.to].lng]], { color: '#eb5757', weight: 3, dashArray: '2 6', interactive: false }).addTo(group)
    }

    if (showCapacity) {
      for (const z of data.zones) {
        const at = zoneCentres[z.zone]
        if (!at) continue
        const marker = L.marker(at, {
          icon: L.divIcon({
            className: '',
            html: `<div style="font:500 10px 'IBM Plex Sans';background:#14171bd9;border:1px solid #363c44;color:#e4e6e9;padding:1px 5px;border-radius:2px;white-space:nowrap;width:max-content;transform:translateX(-50%)">${z.zone} <span style="color:#4cb782;font-family:'IBM Plex Mono'">${z.capacity} ${z.capacity === 1 ? 'seat' : 'seats'}</span></div>`,
            iconSize: [0, 0], iconAnchor: [0, 8],
          }),
        }).addTo(group)
        marker.on('click', () => {
          setZoneName(z.zone)
          setCellId(null)
        })
      }
    }

    if (!fitted.current && data.cells.length) {
      map.fitBounds(L.latLngBounds(data.cells.map((c: any) => [c.lat, c.lng])).pad(0.12))
      fitted.current = true
    }
    return () => {
      group.remove()
    }
  }, [map, data, stops, showCapacity, cellId, zoneCentres])

  const cell = data?.cells.find((c: any) => c.id === cellId)
  const zone = data?.zones.find((z: any) => z.zone === zoneName)
  const unresolved = data?.cells.reduce((n: number, c: any) => n + c.unresolved, 0) ?? 0
  const hottest = data?.cells.reduce((a: any, c: any) => (!a || c.affected > a.affected ? c : a), null)
  const select = 'op-input w-full'

  return (
    <>
      <PageHeader
        title="Disruption heat map"
        sub={<span className="inline-flex items-center gap-1.5"><ShieldAlert size={12} className="text-op-signal" /> Operator only, enforced by the API. Aggregated to about 1 km cells, with no names or exact locations. Simulated data.</span>}
      />
      {error && <p className="mb-2 text-xs text-op-bad">{error}</p>}

      <StatRow cols={4}>
        <Stat label="Passengers shown" value={data?.total ?? '–'} />
        <Stat label="Unresolved here" value={unresolved} tone={unresolved ? 'bad' : undefined} />
        <Stat label="Active cells" value={data?.cells.length ?? '–'} />
        <Stat label="Peak cell" value={hottest?.affected ?? 0} sub={hottest ? `${hottest.zone} zone` : 'No demand'} />
      </StatRow>

      <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_280px]">
        <div className="relative min-w-0 self-start">
          <div ref={ref} className="op-map h-[calc(100vh-250px)] min-h-96 rounded border border-op-line" />
          <div className="absolute bottom-6 left-3 z-[1000] w-44 rounded-sm border border-op-line-strong bg-op-panel/95 p-2">
            <p className="text-[11px] text-op-muted">Passengers per cell</p>
            <div className="mt-1 h-2 rounded-[1px]" style={{ background: SCALE_CSS }} />
            <div className="num mt-0.5 flex justify-between text-[10px] text-op-muted"><span>1</span><span>{data?.max_intensity ?? 0}</span></div>
            <p className="mt-1.5 flex items-center gap-1.5 text-[10px] text-op-muted"><span className="size-2.5 border border-[#ff8a80]" /> Cell with unresolved demand</p>
            <p className="mt-0.5 flex items-center gap-1.5 text-[10px] text-op-muted"><span className="w-2.5 border-t border-dashed border-op-signal" /> Disrupted corridor</p>
          </div>
        </div>

        <div className="grid content-start gap-3">
          <Panel title="Filters">
            <div className="grid gap-2 text-xs text-op-muted">
              <label className="grid gap-1">View
                <select className={select} value={layer} onChange={(e) => { setLayer(e.target.value); setCellId(null) }}>
                  <option value="origin">Where passengers are</option>
                  <option value="destination">Where passengers are going</option>
                </select>
              </label>
              <label className="grid gap-1">Allocation status
                <select className={select} value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="all">All affected</option>
                  <option value="unresolved">Unresolved only</option>
                  <option value="official">Official seat</option>
                  <option value="carpool">Carpool confirmed</option>
                  <option value="review">Needs review</option>
                </select>
              </label>
              <label className="grid gap-1">Disruption
                <select className={select} value={disruption} onChange={(e) => setDisruption(e.target.value)}>
                  <option value="">All disruptions</option>
                  {disruptions?.map((d: any) => <option key={d.id} value={d.id}>{d.code}</option>)}
                </select>
              </label>
              <label className="grid gap-1">Destination
                <select className={select} value={destination} onChange={(e) => setDestination(e.target.value)}>
                  <option value="">All destinations</option>
                  {stops?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1">Departing from
                  <select className={select} value={from} onChange={(e) => setFrom(e.target.value)}>
                    <option value="">Any</option>
                    {TIMES.map((t) => <option key={t} value={t}>{hhmm(t)}</option>)}
                  </select>
                </label>
                <label className="grid gap-1">Until
                  <select className={select} value={to} onChange={(e) => setTo(e.target.value)}>
                    <option value="">Any</option>
                    {TIMES.map((t) => <option key={t} value={t}>{hhmm(t)}</option>)}
                  </select>
                </label>
              </div>
              <label className="flex items-center gap-2 text-op-text"><input type="checkbox" checked={showCapacity} onChange={(e) => setShowCapacity(e.target.checked)} /> Show capacity by zone</label>
            </div>
          </Panel>

          <Panel title="Area inspector">
            {cell ? (
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                <dt className="col-span-2 text-op-muted">{cell.zone} zone, 1 km cell</dt>
                {[['Affected', cell.affected], ['Unresolved', cell.unresolved], ['Official', cell.official], ['Carpool', cell.carpool]].map(([k, v]) => (
                  <div key={k as string}><dt className="text-[11px] text-op-muted">{k}</dt><dd className="num text-base">{v}</dd></div>
                ))}
                <div className="col-span-2 mt-1 border-t border-op-line pt-2">
                  <dt className="text-[11px] text-op-muted">Top destinations</dt>
                  {cell.top_destinations.map((d: any) => <dd key={d.name} className="flex justify-between"><span>{d.name}</span><span className="num">{d.passengers}</span></dd>)}
                </div>
              </dl>
            ) : zone ? (
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                <dt className="col-span-2 text-op-muted">{zone.zone} zone</dt>
                {[['Affected', zone.affected], ['Unresolved', zone.unresolved], ['Seats free', zone.capacity], ['Inbound demand', zone.destination_demand]].map(([k, v]) => (
                  <div key={k as string}><dt className="text-[11px] text-op-muted">{k}</dt><dd className="num text-base">{v}</dd></div>
                ))}
              </dl>
            ) : <Empty>Select a grid cell or zone label on the map.</Empty>}
          </Panel>

          <Panel title="Demand against capacity" flush>
            <table className="op-table">
              <thead><tr><th>Zone</th><th className="text-right!">Affected</th><th className="text-right!">Unres.</th><th className="text-right!">Seats</th></tr></thead>
              <tbody>
                {data?.zones.map((z: any) => (
                  <tr key={z.zone} className="row-link" onClick={() => { setZoneName(z.zone); setCellId(null) }}>
                    <td>{z.zone}</td>
                    <td className="num text-right">{z.affected}</td>
                    <td className={`num text-right ${z.unresolved ? 'text-op-bad' : 'text-op-muted'}`}>{z.unresolved}</td>
                    <td className="num text-right text-op-good">{z.capacity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-3 py-2 text-[11px] text-op-faint">Seats counts free seats on vehicles calling in each zone. One vehicle can serve several zones, so the column doesn't add up to a total.</p>
          </Panel>
        </div>
      </div>
    </>
  )
}
