import type { LucideIcon } from 'lucide-react'
import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }) {
  const look = {
    primary: 'bg-px-accent text-white shadow-card hover:bg-px-accent-strong',
    secondary: 'bg-px-mid text-px-accent hover:bg-px-high',
    quiet: 'text-px-muted underline underline-offset-2 hover:text-px-ink',
    danger: 'text-px-bad hover:bg-px-bad-soft',
  }[variant]
  const size = variant === 'quiet' ? 'min-h-11 px-1 py-1 text-sm' : 'min-h-12 px-5 py-2.5'
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${size} ${look} ${className}`}
    />
  )
}

export function Card({ children, className = '', flush = false }: { children: ReactNode; className?: string; flush?: boolean }) {
  return <section className={`rounded-2xl bg-px-card shadow-card ${flush ? 'overflow-hidden' : 'p-5'} ${className}`}>{children}</section>
}

export type Tone = 'good' | 'info' | 'warn' | 'neutral' | 'bad'

export const toneBox: Record<Tone, string> = {
  good: 'bg-px-good-soft text-px-good',
  info: 'bg-px-mid text-px-accent',
  warn: 'bg-px-warn-soft text-px-warn',
  neutral: 'bg-px-low text-px-muted',
  bad: 'bg-px-bad-soft text-px-bad',
}

export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[13px] font-semibold ${toneBox[tone]}`}>{children}</span>
}

export function Eyebrow({ children, className = 'text-px-muted' }: { children: ReactNode; className?: string }) {
  return <p className={`text-xs font-semibold uppercase tracking-wider ${className}`}>{children}</p>
}

export function IconTile({ icon: Icon, tone = 'info', className = '' }: { icon: LucideIcon; tone?: Tone; className?: string }) {
  return <span className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${toneBox[tone]} ${className}`}><Icon size={20} aria-hidden="true" /></span>
}

export function SectionHead({ icon, title, sub }: { icon: LucideIcon; title: string; sub?: string }) {
  return (
    <div className="flex items-center gap-3">
      <IconTile icon={icon} />
      <div className="min-w-0">
        <h2 className="text-lg font-semibold leading-snug">{title}</h2>
        {sub && <p className="text-sm text-px-muted">{sub}</p>}
      </div>
    </div>
  )
}

/** A full-width tappable checkbox, sized for thumbs. */
export function CheckRow({ icon: Icon, label, ...input }: { icon?: LucideIcon; label: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex min-h-14 cursor-pointer items-center gap-3 rounded-xl bg-px-low px-4 py-3 has-checked:bg-px-high">
      {Icon && <Icon size={20} className="shrink-0 text-px-accent" aria-hidden="true" />}
      <span className="min-w-0 flex-1 text-[15px] font-medium">{label}</span>
      <input type="checkbox" className="size-5 shrink-0" {...input} />
    </label>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-semibold">{label}</span>
      {hint && <span className="block text-sm text-px-muted">{hint}</span>}
      <span className="mt-1 block">{children}</span>
    </label>
  )
}

const Flash = createContext<(text: string, bad?: boolean) => void>(() => {})
export const useFlash = () => useContext(Flash)

export function FlashHost({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<{ text: string; bad: boolean } | null>(null)
  const show = useCallback((text: string, bad = false) => {
    setMessage({ text, bad })
    setTimeout(() => setMessage(null), bad ? 6000 : 3500)
  }, [])
  return (
    <Flash.Provider value={show}>
      {children}
      {message && (
        <div className="fixed inset-x-4 bottom-24 z-50 mx-auto max-w-md md:bottom-6" aria-live="polite">
          <p className={`fade-in rounded-xl px-4 py-3 text-[15px] text-white shadow-lg ${message.bad ? 'bg-px-bad' : 'bg-px-ink'}`}>{message.text}</p>
        </div>
      )}
    </Flash.Provider>
  )
}

export function useDo() {
  const flash = useFlash()
  const [busy, setBusy] = useState(false)
  const run = useCallback(
    async (fn: () => Promise<unknown>, success?: string) => {
      setBusy(true)
      try {
        const result = await fn()
        if (success) flash(success)
        return result ?? true
      } catch (e) {
        flash((e as Error).message, true)
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [flash],
  )
  return { busy, run }
}
