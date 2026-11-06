import { useEffect, useMemo, useState } from 'react'
import { opApi, useLive } from '../../lib/api'
import { L, useMap } from '../../lib/leaflet'
import { Badge, Btn, PageHeader, Panel, ReasonDialog, useAction } from '../ui'

const LINE = { normal: '#707881', cancelled: '#ba1a1a', delayed: '#d97706', closed: '#ba1a1a', vehicle: '#00855d' }

// Stops are close together in the centre, so each label gets its own side to avoid collisions.
const LABEL_SIDE: Record<string, 'left' | 'right' | 'top' | 'bottom'> = {
  SBC: 'left', MGR: 'bottom', YPR: 'left', BSK: 'left', JAY: 'bottom', IND: 'top', MAR: 'bottom', SLK: 'left',
}
const LABEL_OFFSET: Record<string, [number, number]> = { left: [-6, 0], right: [6, 0], top: [0, -6], bottom: [0, 6] }

/** Moves a line sideways so a replacement run sits beside the service it replaces. */
function offset(line: [number, number][], by: number): [number, number][] {
  const [[y1, x1], [y2, x2]] = line
  const length = Math.hypot(y2 - y1, x2 - x1) || 1
  // Normalise direction so a run drawn either way lands on the same side.
  const sign = x2 > x1 || (x2 === x1 && y2 > y1) ? 1 : -1
  const dy = (sign * (x2 - x1) * by) / length
  const dx = (sign * (y1 - y2) * by) / length
  return line.map(([y, x]) => [y + dy, x + dx])
}

/** Schematic: a straight line between stops, not the actual road alignment. */
function shape(seg: any, stops: Record<string, any>): [number, number][] {
  return [[stops[seg.a].lat, stops[seg.a].lng], [stops[seg.b].lat, stops[seg.b].lng]]
}

export default function DisruptionMap() {
  const { ref, map } = useMap(11)
  const { data: stopList } = useLive(opApi, '/network/stops')
  const { data: segments, refetch } = useLive(opApi, '/network/segments')
  const { data: services } = useLive(opApi, '/network/services')
  const { data: runs } = useLive(opApi, '/network/vehicles')
  const { data: heat } = useLive(opApi, '/op/heatmap')
  const { data: stress } = useLive(opApi, '/op/stress')
  const [layers, setLayers] = useState({ services: true, vehicles: true, demand: true })
  const [closing, setClosing] = useState<any>(null)
  const { run } = useAction()

  const stops = useMemo(() => Object.fromEntries((stopList ?? []).map((s: any) => [s.id, s])), [stopList])
  const edgeKey = (a: string, b: string) => [a, b].sort().join('|')
  const bySegment = useMemo(() => Object.fromEntries((segments ?? []).map((s: any) => [edgeKey(s.a, s.b), s])), [segments])

  useEffect(() => {
    if (!map || !stopList || !segments || !services || !runs) return
    const group = L.layerGroup().addTo(map)

    // Which service state applies to each road segment.
    const state: Record<string, string> = {}
    for (const svc of services) {
      for (const branch of svc.branches) {
        for (let i = 0; i + 1 < branch.length; i++) {
          const k = edgeKey(branch[i], branch[i + 1])
          if (svc.status !== 'running' || !state[k]) state[k] = svc.status
        }
      }
    }

    for (const seg of segments) {
      const k = edgeKey(seg.a, seg.b)
      const status = seg.blocked ? 'closed' : state[k]
      if (!layers.services && !seg.blocked) continue
      const color = seg.blocked ? LINE.closed : status === 'cancelled' ? LINE.cancelled : status === 'delayed' ? LINE.delayed : LINE.normal
      const line = L.polyline(shape(seg, stops), {
        color, weight: seg.blocked || status === 'cancelled' ? 3 : 2,
        opacity: status === 'running' || !status ? 0.7 : 0.95,
        dashArray: seg.blocked ? '2 6' : status === 'cancelled' ? '7 5' : undefined,
      }).addTo(group)
      line.on('click', () => setClosing(seg))
      line.bindTooltip(`${seg.a_name} – ${seg.b_name} · ${seg.minutes} min${seg.blocked ? ' · CLOSED' : ''}`, { sticky: true })
    }

    if (layers.vehicles) {
      runs.forEach((v: any, index: number) => {
        if (v.status !== 'available') return
        for (let i = 0; i + 1 < v.stops.length; i++) {
          const seg = bySegment[edgeKey(v.stops[i], v.stops[i + 1])]
          if (seg) L.polyline(offset(shape(seg, stops), 0.0018 * (index + 1)), { color: LINE.vehicle, weight: 1.5, opacity: 0.9, interactive: false }).addTo(group)
        }
        // A lost signal moves the marker to its estimated position; it never disappears.
        const first = stops[v.stops[0]]
        const feed = stress?.telemetry.vehicles.find((f: any) => f.vehicle_id === v.id)
        const at: [number, number] = feed ? [feed.position.lat, feed.position.lng] : [first.lat, first.lng]
        const color = { good: '#006948', warn: '#b45309', bad: '#ba1a1a' }[(feed?.tone ?? 'good') as 'good' | 'warn' | 'bad']
        const note = feed?.position.source === 'dead_reckoning' ? ' (estimated)' : ''
        L.marker(at, {
          icon: L.divIcon({ className: '', html: `<span style="font:600 10px 'Inter Variable';background:${color};color:#fff;padding:1px 5px;border-radius:4px;white-space:nowrap">${v.id}${note}</span>`, iconSize: [34, 14], iconAnchor: [17, 22] }),
          interactive: false,
        }).addTo(group)
      })
    }

    for (const s of stopList) {
      L.circleMarker([s.lat, s.lng], { radius: 3.5, color: '#0d1c2f', weight: 1.5, fillColor: '#fff', fillOpacity: 1 })
        .bindTooltip(s.name, { permanent: true, direction: LABEL_SIDE[s.id] ?? 'right', offset: LABEL_OFFSET[LABEL_SIDE[s.id] ?? 'right'], className: 'stop-label' })
        .addTo(group)
    }

    if (layers.demand && heat) {
      for (const c of heat.cells) {
        L.circleMarker([c.lat, c.lng], {
          radius: 6 + Math.sqrt(c.affected) * 4, color: c.unresolved ? '#ba1a1a' : '#d97706', weight: 1,
          fillColor: c.unresolved ? '#ba1a1a' : '#d97706', fillOpacity: 0.25,
        }).bindPopup(`<b>${c.affected} affected</b><br/>${c.unresolved} unresolved · ${c.official} official · ${c.carpool} carpool`).addTo(group)
      }
    }
    return () => {
      group.remove()
    }
  }, [map, stopList, segments, services, runs, heat, stress, layers, stops, bySegment])

  useEffect(() => {
    if (map && stopList) map.fitBounds(L.latLngBounds(stopList.map((s: any) => [s.lat, s.lng])).pad(0.08))
  }, [map, stopList?.length])

  const closed = segments?.filter((s: any) => s.blocked) ?? []
  const disrupted = services?.filter((s: any) => s.status !== 'running') ?? []
  const toggle = (k: keyof typeof layers) => setLayers((l) => ({ ...l, [k]: !l[k] }))

  return (
    <>
      <PageHeader title="Interactive disruption map" sub="Network state, replacement runs and aggregated demand. Click a road segment to close it." />
      <div className="grid gap-3 lg:grid-cols-[1fr_250px]">
        <div ref={ref} className="op-map h-[calc(100vh-140px)] min-h-96 rounded-xl border border-op-line" />
        <div className="grid content-start gap-3">
          <Panel title="Layers">
            {([['services', 'Service network'], ['vehicles', 'Replacement runs'], ['demand', 'Affected demand']] as const).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 py-0.5 text-xs"><input type="checkbox" checked={layers[k]} onChange={() => toggle(k)} /> {label}</label>
            ))}
          </Panel>
          <Panel title="Legend">
            <ul className="grid gap-1.5 text-xs text-op-muted">
              {[['Running', LINE.normal, 'solid'], ['Cancelled service', LINE.cancelled, 'dashed'], ['Delayed service', LINE.delayed, 'solid'], ['Closed road', LINE.closed, 'dotted'], ['Replacement run', LINE.vehicle, 'solid']].map(([label, color, style]) => (
                <li key={label} className="flex items-center gap-2"><span className="w-6" style={{ borderTop: `2px ${style} ${color}` }} />{label}</li>
              ))}
              <li className="flex items-center gap-2"><span className="ml-1.5 size-3 rounded-full" style={{ background: '#ba1a1a40', border: '1px solid #ba1a1a' }} /><span className="ml-1">Contains unresolved demand</span></li>
            </ul>
          </Panel>
          <Panel title="Network status">
            {!disrupted.length && !closed.length && <p className="text-xs text-op-muted">All services running.</p>}
            <ul className="grid gap-1.5">
              {disrupted.map((s: any) => (
                <li key={s.id} className="flex items-center justify-between gap-2 text-xs"><span className="num">{s.id}</span><Badge tone={s.status === 'cancelled' ? 'bad' : 'warn'}>{s.status === 'delayed' ? `+${s.delay_min} min` : 'Cancelled'}</Badge></li>
              ))}
              {closed.map((s: any) => <li key={s.id} className="text-xs text-op-muted">{s.a_name} – {s.b_name} closed</li>)}
            </ul>
          </Panel>
          <p className="text-[11px] text-op-faint">Simulated network over OpenStreetMap. Lines are schematic, not road alignments, and stop positions are approximate. Demand is aggregated to roughly 1 km cells.</p>
        </div>
      </div>

      {closing && !closing.blocked && (
        <ReasonDialog
          title={`Close ${closing.a_name} – ${closing.b_name}?`}
          body="Vehicles and services divert if a route exists. Confirmed journeys that stop working are flagged for review."
          confirmLabel="Close road"
          danger
          onCancel={() => setClosing(null)}
          onConfirm={(description) => {
            const seg = closing
            setClosing(null)
            run(() => opApi.post('/op/disruptions', { kind: 'route_closure', segment_id: seg.id, description }).then(refetch), 'Road closed and network reassessed')
          }}
        />
      )}
      {closing?.blocked && (
        <div className="fixed bottom-4 left-1/2 z-[1500] -translate-x-1/2 rounded-xl border border-op-line bg-op-raised px-3 py-2 text-xs">
          Already closed. Resolve it from Disruption simulation. <Btn variant="ghost" onClick={() => setClosing(null)}>Dismiss</Btn>
        </div>
      )}
    </>
  )
}
