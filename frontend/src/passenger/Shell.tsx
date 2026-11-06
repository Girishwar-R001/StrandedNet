import { Bell, Car, ClipboardCheck, ListOrdered, LogOut, Ticket, type LucideIcon } from 'lucide-react'
import { useEffect } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { pxApi, useLive } from '../lib/api'
import Logo from '../Logo'
import PageBoundary from '../PageBoundary'
import { FlashHost } from './ui'

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean }

function pageName(path: string) {
  if (path.endsWith('/options')) return 'Your options'
  if (path.endsWith('/journey/new')) return 'Check-in'
  if (path.endsWith('/carpool')) return 'Community carpool'
  if (path.endsWith('/notifications')) return 'Updates'
  return 'My journey'
}

export default function Shell() {
  const navigate = useNavigate()
  const location = useLocation()
  const { data: me, error } = useLive(pxApi, pxApi.token ? '/auth/me' : null)
  const { data: notes } = useLive(pxApi, pxApi.token ? '/me/notifications' : null)
  const { data: journeys } = useLive(pxApi, pxApi.token ? '/me/journeys' : null)
  const { data: disruptions } = useLive(pxApi, pxApi.token ? '/me/disruptions' : null)

  useEffect(() => {
    if (error?.includes('Sign in') || error?.includes('Passenger access')) {
      pxApi.setToken(null)
      navigate('/login', { replace: true })
    }
  }, [error, navigate])

  if (!pxApi.token) return <Navigate to="/login" replace />
  const unread = notes?.filter((n: any) => !n.read).length ?? 0
  const affected = journeys?.find((j: any) => j.status === 'affected')
  const incidents = disruptions ?? []

  // Options belongs to a journey, so the tab only exists while one needs choosing.
  const nav: NavItem[] = [
    { to: '/app/journey/new', label: 'Check-in', icon: ClipboardCheck },
    ...(affected ? [{ to: `/app/journey/${affected.id}/options`, label: 'Options', icon: ListOrdered }] : []),
    { to: '/app', label: 'Journey', icon: Ticket, end: true },
    { to: '/app/carpool', label: 'Carpool', icon: Car },
    { to: '/app/notifications', label: 'Updates', icon: Bell },
  ]

  return (
    <FlashHost>
      <div className={`px-root min-h-full ${location.pathname.endsWith('/options') ? 'pb-40 md:pb-24' : 'pb-24 md:pb-8'}`}>
        <header className="sticky top-0 z-30 bg-px-bg/90 shadow-[0_1px_8px_rgba(0,0,0,0.04)] backdrop-blur-xl">
          <div className="mx-auto grid max-w-5xl gap-1.5 px-4 py-2">
            <div className="flex min-h-11 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <Logo />
                <div className="min-w-0 leading-tight">
                  <p className="truncate font-display text-[17px] font-semibold">The Stranded Network</p>
                  <p className="truncate text-xs text-px-muted">{pageName(location.pathname)}</p>
                </div>
              </div>
              <nav className="hidden items-center gap-1 md:flex">
                {nav.map(({ to, label, end }) => (
                  <NavLink key={to} to={to} end={end} className={({ isActive }) => `rounded-xl px-3 py-2 text-sm font-semibold ${isActive ? 'bg-px-high text-px-accent' : 'text-px-muted hover:bg-px-low hover:text-px-ink'}`}>
                    {label}{to.endsWith('notifications') && unread > 0 ? ` (${unread})` : ''}
                  </NavLink>
                ))}
              </nav>
              <div className="flex shrink-0 items-center gap-1">
                {me && <span aria-hidden="true" className="flex size-9 items-center justify-center rounded-full bg-px-highest text-sm font-semibold text-px-accent">{me.name[0]}</span>}
                <button
                  className="flex size-11 cursor-pointer items-center justify-center rounded-full text-px-muted hover:bg-px-low hover:text-px-ink"
                  aria-label="Sign out"
                  onClick={() => {
                    pxApi.setToken(null)
                    navigate('/login')
                  }}
                >
                  <LogOut size={18} />
                </button>
              </div>
            </div>
            <div className="flex items-center justify-between gap-3 rounded-lg bg-px-mid px-3 py-1">
              <p className="flex min-w-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-wide">
                <span className={`size-2 shrink-0 rounded-full ${incidents.length ? 'bg-[#d97706] motion-safe:animate-pulse' : 'bg-px-good'}`} />
                <span className="truncate">
                  {incidents.length ? `Incident active • ${incidents[0].code}${incidents.length > 1 ? ` +${incidents.length - 1}` : ''}` : 'No active incidents'}
                </span>
              </p>
              <span className="shrink-0 text-[11px] font-medium text-px-muted">Simulated</span>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-2xl px-4 py-5">
          <div className="fade-in" key={location.pathname}><PageBoundary><Outlet /></PageBoundary></div>
          <p className="mt-10 text-center text-[13px] text-px-muted">Demo service. Network, times and passengers are simulated.</p>
        </main>
        <nav className="fixed inset-x-0 bottom-0 z-30 flex h-16 bg-px-card shadow-tray md:hidden">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex flex-1 flex-col items-center justify-center gap-0.5 text-xs ${isActive ? 'font-semibold text-px-accent' : 'font-medium text-px-muted'}`}>
              <span className="relative">
                <Icon size={22} />
                {to.endsWith('notifications') && unread > 0 && <span className="absolute -right-1 -top-0.5 size-2 rounded-full bg-px-bad" />}
              </span>
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </FlashHost>
  )
}
