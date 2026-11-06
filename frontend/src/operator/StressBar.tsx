import {
  CarFront, ChevronDown, Copy, Handshake, MapPinOff, Play, RadioTower, RefreshCw, ShieldAlert, TriangleAlert, Users, Zap,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { opApi, useLive } from '../lib/api'
import { hhmm } from '../lib/format'
import { Badge, Btn, ReasonDialog, useAction, type Tone } from './ui'

export function TelemetryBadge({ tone, label }: { tone: Tone; label: string }) {
  return <Badge tone={tone}>{label}</Badge>
}

function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'good' | 'bad' | 'warn' }) {
  const color = { good: 'text-op-good', bad: 'text-op-bad', warn: 'text-op-signal' }[tone ?? 'good']
  return (
    <div className={`min-w-0 rounded-lg px-3 py-2 ${tone === 'good' ? 'bg-px-good-soft' : 'bg-op-raised'}`}>
      <p className="truncate text-[11px] font-medium text-op-muted">{label}</p>
      <p className={`num font-display text-xl font-semibold leading-tight ${tone ? color : ''}`}>{value}</p>
      {sub && <p className="truncate text-[11px] text-op-muted">{sub}</p>}
    </div>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid min-w-0 gap-1 lg:grid-cols-[150px_minmax(0,1fr)] lg:items-center lg:gap-3">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-op-faint">{title}</p>
      <div className="flex min-w-0 flex-wrap gap-1.5">{children}</div>
    </div>
  )
}

const FAULT_RESULT: Record<string, (r: any) => string> = {
  spike: (r) => `Spike rejected: reported ${r.reported} seats, max ${r.max}. Database still shows ${r.true_available} free.`,
  storm: (r) => `${r.dropped} of ${r.frames} repeated frames dropped. ${r.reroutes_triggered} re-routes triggered.`,
  gps: () => 'Vehicle C lost GPS. Dead reckoning from its last verified position.',
  conflict: (r) => r.outcome === 'quarantined'
    ? `NON-DESTRUCTIVE LOCK ACTIVE: ${r.confirmed_seats_preserved} confirmed seats preserved. Operator review needed.`
    : 'Logged, not quarantined: Vehicle A has no confirmed passengers yet. Run allocation first.',
}

/** The judge's single place to run every scenario and watch the numbers move. */
export default function StressBar({ demo }: { demo: boolean }) {
  const { data } = useLive(opApi, '/op/stress')
  const { busy, run } = useAction()
  const { pathname } = useLocation()
  // Open on the Overview, folded elsewhere so maps and tables stay on screen. KPIs always show.
  const [choice, setChoice] = useState<boolean | null>(null)
  const open = choice ?? pathname === '/operator'
  const [reviewing, setReviewing] = useState<{ id: string; decision: 'keep' | 'withdraw' } | null>(null)
  if (!data) return null

  const { kpis: k, telemetry: t, corridors, scenario } = data
  const conflicts = t.vehicles.filter((v: any) => v.conflict)
  const surge = scenario.name === 'surge' && corridors.length > 0
  const unsettled = corridors.reduce((n: number, c: any) => n + c.waiting, 0)
  const pending = corridors.reduce((n: number, c: any) => n + c.proposed, 0)
  const fault = (name: string) => run(() => opApi.post(`/demo/telemetry/${name}`), FAULT_RESULT[name])

  return (
    <section className="mb-4 overflow-hidden rounded-xl bg-op-panel shadow-card" aria-label="Stress test controls">
      <header className="flex min-h-11 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-op-line px-4 py-1.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><Zap size={15} className="text-op-primary" /> Judge stress-test controls</h2>
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-xs text-op-muted">{scenario.label}</span>
          <TelemetryBadge tone={t.tone} label={t.label} />
          <button type="button" aria-expanded={open} aria-label={open ? 'Collapse controls' : 'Expand controls'} className="cursor-pointer rounded-lg p-1 text-op-muted hover:bg-op-raised" onClick={() => setChoice(!open)}>
            <ChevronDown size={16} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-2 p-3 md:grid-cols-3 xl:grid-cols-5">
        <Kpi label="Stranded Passengers" value={k.stranded_passengers} />
        <Kpi label="Official Seats Available" value={k.official_seats} sub={`${k.official_seats_free} still free`} />
        <Kpi label="Over-Allocation Count" value={k.over_allocation} tone={k.over_allocation ? 'bad' : 'good'} sub={k.over_allocation ? 'Investigate now' : 'Atomic lock holding'} />
        <Kpi label="Tier-2 Carpool Rollover" value={k.carpool_rollover} sub={`${k.carpool_confirmed} confirmed by consent`} />
        <Kpi
          label="Telemetry Sanitizer Status" value={t.spikes_rejected + t.conflicts} tone={t.conflicts ? 'bad' : t.stale ? 'warn' : undefined}
          sub={`${t.spikes_rejected} spikes, ${t.conflicts} conflicts, ${t.duplicates_dropped} deduped`}
        />
      </div>

      {conflicts.map((v: any) => (
        <div key={v.vehicle_id} role="alert" className="mx-3 mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-px-bad-soft px-3 py-2 text-[13px]">
          <p className="flex min-w-0 items-start gap-2 text-op-bad">
            <ShieldAlert size={16} className="mt-0.5 shrink-0" />
            <span><strong className="font-semibold">NON-DESTRUCTIVE LOCK ACTIVE on {v.name} ({v.vehicle_id}).</strong> Confirmed bookings are untouched until you decide.</span>
          </p>
          <div className="flex gap-1.5">
            <Btn onClick={() => setReviewing({ id: v.vehicle_id, decision: 'keep' })}>Verified running</Btn>
            <Btn variant="danger" onClick={() => setReviewing({ id: v.vehicle_id, decision: 'withdraw' })}>Confirm offline</Btn>
          </div>
        </div>
      ))}

      {surge && (
        <div className="mx-3 mb-3 rounded-lg bg-px-warn-soft px-3 py-2">
          <p className="flex flex-wrap items-center gap-x-2 text-[13px] font-semibold text-px-warn">
            <TriangleAlert size={15} /> Surge Carpool Mobilisation
            <span className="font-normal">{k.carpool_rollover} stranded passengers pooled across {corridors.length} corridors. Names and exact locations are never shown.</span>
          </p>
          <ul className="mt-1.5 grid gap-1.5 sm:grid-cols-2 xl:grid-cols-4">
            {corridors.map((c: any) => (
              <li key={c.label} className="rounded-lg bg-op-panel px-2.5 py-1.5 text-xs">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-semibold">{c.label}: {c.name}</span>
                  <span className="num font-display text-base font-semibold">{c.passengers}</span>
                </span>
                <span className="num block text-[11px] text-op-muted">{hhmm(c.window_start)}–{hhmm(c.window_end)} · {c.waiting} waiting · {c.proposed} proposed · {c.confirmed} confirmed</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {open && demo && (
        <div className="grid gap-2 border-t border-op-line p-3">
          <Group title="Scenario presets">
            <Btn disabled={busy} onClick={() => run(() => opApi.post('/demo/scenario/baseline'), 'Baseline loaded: 24 passengers, 20 seats')}><RefreshCw size={13} /> Load Baseline Scenario (24 Pax / 20 Seats)</Btn>
            <Btn variant="danger" disabled={busy} onClick={() => run(() => opApi.post('/demo/scenario/surge'), 'Crisis surge loaded: 72 passengers, 10 seats')}><Zap size={13} /> Crisis Surge (72 Pax / 10 Seats)</Btn>
          </Group>
          <Group title="Run">
            <Btn variant="primary" disabled={busy || !k.stranded_passengers} onClick={() => run(() => opApi.post('/demo/run-allocation'), (r) => `${r.seats} official seats reserved. ${r.rollover} passengers rolled over to Tier 2.`)}><Play size={13} /> Run Smart Allocation</Btn>
            <Btn disabled={busy || !unsettled} onClick={() => run(() => opApi.post('/demo/carpool-wave'), (r) => `${r.drivers} drivers proposed ${r.seats_proposed} seats. ${r.still_unmatched} still unmatched.`)}><CarFront size={13} /> Simulate Community Carpool Wave</Btn>
            <Btn disabled={busy || !pending} onClick={() => run(() => opApi.post('/demo/carpool-consent'), (r) => `${r.passengers_accepted} parties accepted, ${r.matches_confirmed} drivers confirmed.`)}><Handshake size={13} /> Simulate Mutual Consent</Btn>
          </Group>
          <Group title="Telemetry chaos injection">
            <Btn disabled={busy} onClick={() => fault('spike')}><Users size={13} /> Seat Spike (+42 Phantom Seats)</Btn>
            <Btn disabled={busy} onClick={() => fault('storm')}><Copy size={13} /> Repeated Packet Storm</Btn>
            <Btn disabled={busy} onClick={() => fault('gps')}><MapPinOff size={13} /> Missing GPS Feed</Btn>
            <Btn disabled={busy} onClick={() => fault('conflict')}><RadioTower size={13} /> Conflicting Sensor Drop</Btn>
            {t.stale > 0 && <Btn variant="ghost" disabled={busy} onClick={() => run(() => opApi.post('/demo/telemetry/restore'), 'GPS feed restored')}>Restore GPS</Btn>}
          </Group>
        </div>
      )}

      {reviewing && (
        <ReasonDialog
          title={reviewing.decision === 'keep' ? `Clear the sensor conflict on ${reviewing.id}?` : `Take ${reviewing.id} out of service?`}
          body={reviewing.decision === 'keep'
            ? 'Confirm you have verified this vehicle is running. Bookings stay as they are.'
            : 'Its passengers lose their physical seats and move to Unresolved demand for your decision. Each one is told.'}
          confirmLabel={reviewing.decision === 'keep' ? 'Clear conflict' : 'Withdraw vehicle'}
          danger={reviewing.decision === 'withdraw'}
          onCancel={() => setReviewing(null)}
          onConfirm={(reason) => {
            const { id, decision } = reviewing
            setReviewing(null)
            run(() => opApi.post(`/op/telemetry/${id}/resolve`, { decision, reason }), 'Decision recorded in the audit log')
          }}
        />
      )}
    </section>
  )
}
