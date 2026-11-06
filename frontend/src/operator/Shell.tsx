import {
  Activity, BrainCircuit, Bus, Car, FileClock, Flame, GitMerge, LayoutDashboard, ListChecks, LogOut, Map as MapIcon,
  Menu, ScrollText, TriangleAlert, Users, X, Zap, type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { opApi, useLive } from '../lib/api'
import { hhmm } from '../lib/format'
import Logo from '../Logo'
import PageBoundary from '../PageBoundary'
import StressBar, { TelemetryBadge } from './StressBar'
import { ToastHost } from './ui'

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean; badge?: boolean }

const NAV: { group: string; items: NavItem[] }[] = [
  { group: 'Monitor', items: [
    { to: '/operator', label: 'Overview', icon: LayoutDashboard, end: true },
    { to: '/operator/map', label: 'Disruption map', icon: MapIcon },
    { to: '/operator/heatmap', label: 'Heat map', icon: Flame },
  ] },
  { group: 'Demand', items: [
    { to: '/operator/passengers', label: 'Passengers', icon: Users },
    { to: '/operator/groups', label: 'Grouping', icon: GitMerge },
    { to: '/operator/preferences', label: 'Preferences', icon: ListChecks },
    { to: '/operator/unresolved', label: 'Unresolved demand', icon: TriangleAlert, badge: true },
  ] },
  { group: 'Supply', items: [
    { to: '/operator/vehicles', label: 'Vehicles', icon: Bus },
    { to: '/operator/allocation', label: 'Smart allocation', icon: BrainCircuit },
    { to: '/operator/carpool', label: 'Community carpool', icon: Car },
  ] },
  { group: 'Control', items: [
    { to: '/operator/simulation', label: 'Disruption simulation', icon: Zap },
    { to: '/operator/explanations', label: 'Explanations', icon: ScrollText },
    { to: '/operator/audit', label: 'Audit log', icon: FileClock },
  ] },
]

export default function Shell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const { data: meta } = useLive(opApi, '/meta')
  const { data: overview, error } = useLive(opApi, opApi.token ? '/op/overview' : null)
  const { data: stress } = useLive(opApi, opApi.token ? '/op/stress' : null)

  useEffect(() => setOpen(false), [location.pathname])
  useEffect(() => {
    if (error?.includes('Sign in') || error?.includes('Operator access')) {
      opApi.setToken(null)
      navigate('/operator/login', { replace: true })
    }
  }, [error, navigate])

  if (!opApi.token) return <Navigate to="/operator/login" replace />

  const unresolved = overview ? (overview.by_state.unresolved ?? 0) + (overview.by_state.needs_review ?? 0) : 0
  const disruptions = overview?.active_disruptions ?? []

  return (
    <ToastHost>
      <div className="op-root flex h-full">
        {open && <button aria-label="Close menu" className="fixed inset-0 z-[1100] bg-[#0f172a]/45 lg:hidden" onClick={() => setOpen(false)} />}
        <aside className={`${open ? 'translate-x-0' : '-translate-x-full'} fixed inset-y-0 left-0 z-[1200] flex w-60 shrink-0 flex-col border-r border-op-line bg-op-panel transition-transform lg:static lg:translate-x-0`}>
          <div className="flex h-14 items-center justify-between gap-2 px-4">
            <span className="flex min-w-0 items-center gap-2 font-display text-[15px] font-semibold"><Logo size={28} /> <span className="truncate">Stranded Network</span></span>
            <button className="cursor-pointer text-op-muted lg:hidden" aria-label="Close menu" onClick={() => setOpen(false)}><X size={16} /></button>
          </div>
          <nav className="flex-1 overflow-y-auto px-2 py-2">
            {NAV.map(({ group, items }) => (
              <div key={group} className="mb-3">
                <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-op-faint">{group}</p>
                {items.map(({ to, label, icon: Icon, end, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={end}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${isActive ? 'bg-px-high font-semibold text-op-primary' : 'font-medium text-op-muted hover:bg-op-raised hover:text-op-text'}`
                    }
                  >
                    <Icon size={16} strokeWidth={1.75} />
                    <span className="flex-1 truncate">{label}</span>
                    {badge && unresolved > 0 && <span className="num rounded-full bg-px-bad-soft px-1.5 text-[11px] font-semibold text-op-bad">{unresolved}</span>}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
          <button
            className="flex cursor-pointer items-center gap-2 border-t border-op-line px-4 py-3 text-[13px] font-medium text-op-muted hover:text-op-text"
            onClick={() => {
              opApi.setToken(null)
              navigate('/operator/login')
            }}
          >
            <LogOut size={13} /> Sign out
          </button>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-op-line bg-op-panel px-3 sm:px-5">
            <button className="cursor-pointer text-op-muted lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu size={18} /></button>
            <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg bg-px-mid px-3 py-1.5 text-xs">
              {disruptions.length ? (
                <>
                  <Activity size={13} className="shrink-0 text-op-signal" />
                  <span className="num shrink-0 font-semibold uppercase tracking-wide text-op-signal">{disruptions[0].code}</span>
                  <span className="truncate text-op-muted">{disruptions[0].description}</span>
                  {disruptions.length > 1 && <span className="shrink-0 text-op-faint">+{disruptions.length - 1} more</span>}
                </>
              ) : (
                <span className="text-op-muted">Network normal</span>
              )}
            </div>
            {stress && <span className="hidden md:inline"><TelemetryBadge tone={stress.telemetry.tone} label={stress.telemetry.label} /></span>}
            <span className="hidden text-[11px] text-op-faint sm:inline">Simulated network</span>
            <span className="num shrink-0 font-display text-sm font-semibold">{meta ? hhmm(meta.now) : '--:--'}</span>
          </header>
          <main className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-5">
            <div className="fade-in mx-auto max-w-[1500px]" key={location.pathname}>
              <StressBar demo={!!meta?.demo_mode} />
              <PageBoundary><Outlet /></PageBoundary>
            </div>
          </main>
        </div>
      </div>
    </ToastHost>
  )
}
