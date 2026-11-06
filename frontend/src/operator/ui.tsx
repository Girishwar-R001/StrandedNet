import { X } from 'lucide-react'
import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'

export type Tone = 'neutral' | 'good' | 'bad' | 'warn' | 'info'

const toneText: Record<Tone, string> = {
  neutral: 'text-op-muted',
  good: 'text-op-good',
  bad: 'text-op-bad',
  warn: 'text-op-signal',
  info: 'text-op-info',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs ${toneText[tone]}`}>
      <span className="size-1.5 rounded-full bg-current" />
      {children}
    </span>
  )
}

export function Btn({
  variant = 'default',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'danger' | 'ghost' }) {
  const look = {
    default: 'border-op-line-strong bg-op-raised text-op-text hover:border-op-faint',
    primary: 'border-op-signal bg-op-signal font-medium text-[#1a1407] hover:brightness-110',
    danger: 'border-op-line-strong bg-op-raised text-op-bad hover:border-op-bad',
    ghost: 'border-transparent text-op-muted hover:text-op-text',
  }[variant]
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-[3px] border px-2.5 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40 ${look} ${className}`}
    />
  )
}

export function Panel({
  title,
  action,
  children,
  className = '',
  flush = false,
}: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  flush?: boolean
}) {
  return (
    <section className={`min-w-0 rounded border border-op-line bg-op-panel ${className}`}>
      {(title || action) && (
        <header className="flex min-h-9 items-center justify-between gap-3 border-b border-op-line px-3 py-1.5">
          <h2 className="text-xs font-medium text-op-text">{title}</h2>
          {action}
        </header>
      )}
      <div className={flush ? 'overflow-x-auto' : 'p-3'}>{children}</div>
    </section>
  )
}

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: Tone
}) {
  return (
    <div className="min-w-0 bg-op-panel px-3 py-2.5">
      <p className="truncate text-[11px] text-op-muted">{label}</p>
      <p className={`num mt-1 text-2xl leading-none ${tone ? toneText[tone] : 'text-op-text'}`}>{value}</p>
      {sub && <p className="mt-1.5 truncate text-[11px] text-op-faint">{sub}</p>}
    </div>
  )
}

export function StatRow({ children, cols = 6 }: { children: ReactNode; cols?: number }) {
  const grid: Record<number, string> = {
    3: 'grid-cols-3',
    4: 'grid-cols-2 sm:grid-cols-4',
    5: 'grid-cols-2 sm:grid-cols-5',
    6: 'grid-cols-2 sm:grid-cols-3 xl:grid-cols-6',
  }
  return <div className={`grid gap-px overflow-hidden rounded border border-op-line bg-op-line ${grid[cols]}`}>{children}</div>
}

export function PageHeader({ title, sub, action }: { title: string; sub?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-base font-medium">{title}</h1>
        {sub && <p className="mt-0.5 max-w-3xl text-xs text-op-muted">{sub}</p>}
      </div>
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-3 py-6 text-center text-xs text-op-muted">{children}</p>
}

export function Loading({ error }: { error?: string | null }) {
  return <p className={`py-10 text-center text-xs ${error ? 'text-op-bad' : 'text-op-muted'}`}>{error ?? 'Loading…'}</p>
}

const STATE: Record<string, [string, Tone]> = {
  unaffected: ['Unaffected', 'neutral'],
  unresolved: ['Unresolved', 'bad'],
  proposed: ['Proposed', 'info'],
  approved: ['Approved', 'info'],
  official_confirmed: ['Seat confirmed', 'good'],
  confirmed: ['Seat confirmed', 'good'],
  needs_review: ['Needs review', 'warn'],
  carpool_confirmed: ['Carpool confirmed', 'good'],
  self_resolved: ['Self-resolved', 'neutral'],
  rejected: ['Rejected', 'neutral'],
  cancelled: ['Cancelled', 'neutral'],
}

export function StateBadge({ state }: { state: string }) {
  const [label, tone] = STATE[state] ?? [state, 'neutral']
  return <Badge tone={tone}>{label}</Badge>
}

/** A modal that insists on a reason. Overrides and releases must always be attributable. */
export function ReasonDialog({
  title,
  body,
  confirmLabel,
  danger,
  noReason,
  onCancel,
  onConfirm,
}: {
  title: string
  body?: ReactNode
  confirmLabel: string
  danger?: boolean
  noReason?: boolean
  onCancel: () => void
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  const ready = noReason || reason.trim().length >= 3
  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label={title}>
      <form
        className="w-full max-w-md rounded border border-op-line-strong bg-op-panel p-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (ready) onConfirm(reason.trim())
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-sm font-medium">{title}</h2>
          <button type="button" aria-label="Close" onClick={onCancel} className="cursor-pointer text-op-muted hover:text-op-text">
            <X size={16} />
          </button>
        </div>
        {body && <div className="mt-2 text-xs text-op-muted">{body}</div>}
        {!noReason && (
          <label className="mt-3 block text-xs text-op-muted">
            Reason (recorded in the audit log)
            <textarea autoFocus rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className="op-input mt-1 w-full resize-none" />
          </label>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <Btn onClick={onCancel}>Cancel</Btn>
          <Btn type="submit" variant={danger ? 'danger' : 'primary'} disabled={!ready}>
            {confirmLabel}
          </Btn>
        </div>
      </form>
    </div>
  )
}

type ToastItem = { id: number; text: string; bad: boolean }
const ToastContext = createContext<(text: string, bad?: boolean) => void>(() => {})
export const useToast = () => useContext(ToastContext)

export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const push = useCallback((text: string, bad = false) => {
    const id = Date.now() + Math.random()
    setItems((list) => [...list, { id, text, bad }])
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), bad ? 7000 : 3500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[3000] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`fade-in rounded border bg-op-raised px-3 py-2 text-xs ${t.bad ? 'border-op-bad text-op-text' : 'border-op-line-strong text-op-text'}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/** Wraps an API action with a busy flag and toast feedback. */
export function useAction() {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const run = useCallback(
    async (fn: () => Promise<unknown>, success?: string | ((r: any) => string)) => {
      setBusy(true)
      try {
        const result = await fn()
        if (success) toast(typeof success === 'function' ? success(result) : success)
        return result
      } catch (e) {
        toast((e as Error).message, true)
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [toast],
  )
  return { busy, run }
}
