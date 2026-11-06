import { Bell, Car, Home, LogOut } from 'lucide-react'
import { useEffect } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { pxApi, useLive } from '../lib/api'
import PageBoundary from '../PageBoundary'
import { FlashHost } from './ui'

const NAV = [
  { to: '/app', label: 'My journey', icon: Home, end: true },
  { to: '/app/carpool', label: 'Carpool', icon: Car },
  { to: '/app/notifications', label: 'Updates', icon: Bell },
]

export default function Shell() {
  const navigate = useNavigate()
  const location = useLocation()
  const { data: me, error } = useLive(pxApi, pxApi.token ? '/auth/me' : null)
  const { data: notes } = useLive(pxApi, pxApi.token ? '/me/notifications' : null)

  useEffect(() => {
    if (error?.includes('Sign in') || error?.includes('Passenger access')) {
      pxApi.setToken(null)
      navigate('/login', { replace: true })
    }
  }, [error, navigate])

  if (!pxApi.token) return <Navigate to="/login" replace />
  const unread = notes?.filter((n: any) => !n.read).length ?? 0

  return (
    <FlashHost>
      <div className="px-root min-h-full pb-20 md:pb-8">
        <header className="sticky top-0 z-30 border-b border-px-line bg-px-bg/95">
          <div className="mx-auto flex h-14 max-w-2xl items-center justify-between gap-4 px-4">
            <span className="font-semibold tracking-tight">The Stranded Network</span>
            <nav className="hidden items-center gap-1 md:flex">
              {NAV.map(({ to, label, end }) => (
                <NavLink key={to} to={to} end={end} className={({ isActive }) => `rounded-lg px-3 py-1.5 text-[15px] ${isActive ? 'bg-px-accent-soft font-medium text-px-accent' : 'text-px-muted hover:text-px-ink'}`}>
                  {label}{to.endsWith('notifications') && unread > 0 ? ` (${unread})` : ''}
                </NavLink>
              ))}
            </nav>
            <button
              className="flex cursor-pointer items-center gap-1.5 text-sm text-px-muted hover:text-px-ink"
              onClick={() => {
                pxApi.setToken(null)
                navigate('/login')
              }}
            >
              <span className="hidden sm:inline">{me?.name.split(' ')[0]}</span> <LogOut size={15} aria-label="Sign out" />
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-2xl px-4 py-6">
          <div className="fade-in" key={location.pathname}><PageBoundary><Outlet /></PageBoundary></div>
          <p className="mt-10 text-center text-[13px] text-px-muted">Demo service. Network, times and passengers are simulated.</p>
        </main>
        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-3 border-t border-px-line bg-px-card md:hidden">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `relative flex flex-col items-center gap-0.5 py-2 text-xs ${isActive ? 'text-px-accent' : 'text-px-muted'}`}>
              <Icon size={20} />
              {label}
              {to.endsWith('notifications') && unread > 0 && <span className="absolute right-[32%] top-1.5 size-2 rounded-full bg-px-bad" />}
            </NavLink>
          ))}
        </nav>
      </div>
    </FlashHost>
  )
}
