import { Bell, CircleCheck, TriangleAlert } from 'lucide-react'
import { useEffect } from 'react'
import { pxApi, useLive } from '../../lib/api'
import { timeAgo } from '../../lib/format'

const ICON = { success: CircleCheck, warning: TriangleAlert, info: Bell } as const
const COLOR = { success: 'text-px-accent', warning: 'text-px-warn', info: 'text-px-info' } as const

export default function Notifications() {
  const { data } = useLive(pxApi, '/me/notifications')
  const unread = data?.some((n: any) => !n.read)

  useEffect(() => {
    if (unread) {
      const t = setTimeout(() => pxApi.post('/me/notifications/read'), 1500)
      return () => clearTimeout(t)
    }
  }, [unread])

  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold tracking-tight">Updates</h1>
      {data?.length === 0 && <p className="text-px-muted">Nothing yet. We'll let you know as soon as anything changes.</p>}
      <ul className="grid gap-px overflow-hidden rounded-xl border border-px-line bg-px-line">
        {data?.map((n: any) => {
          const kind = n.kind as keyof typeof ICON
          const Icon = ICON[kind] ?? Bell
          return (
            <li key={n.id} className="flex gap-3 bg-px-card p-4">
              <Icon size={20} className={`mt-0.5 shrink-0 ${COLOR[kind] ?? ''}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <p className={n.read ? 'font-medium' : 'font-semibold'}>{n.title}</p>
                  <span className="shrink-0 text-[13px] text-px-muted">{timeAgo(n.created_at)}</span>
                </div>
                {n.body && <p className="text-[15px] text-px-muted">{n.body}</p>}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
