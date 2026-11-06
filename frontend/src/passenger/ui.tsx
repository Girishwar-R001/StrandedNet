import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }) {
  const look = {
    primary: 'bg-px-accent text-white hover:brightness-110',
    secondary: 'border border-[#cfc8b9] bg-white text-px-ink hover:border-px-ink',
    quiet: 'text-px-muted underline underline-offset-2 hover:text-px-ink',
    danger: 'border border-[#e2c3bf] bg-white text-px-bad hover:border-px-bad',
  }[variant]
  const size = variant === 'quiet' ? 'px-1 py-1 text-sm' : 'px-4 py-2.5'
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg font-medium disabled:cursor-not-allowed disabled:opacity-50 ${size} ${look} ${className}`}
    />
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-px-line bg-px-card p-5 ${className}`}>{children}</section>
}

export type Tone = 'good' | 'info' | 'warn' | 'neutral' | 'bad'

export const toneBox: Record<Tone, string> = {
  good: 'bg-px-accent-soft text-px-accent',
  info: 'bg-px-info-soft text-px-info',
  warn: 'bg-px-warn-soft text-px-warn',
  neutral: 'bg-[#ece8df] text-px-muted',
  bad: 'bg-[#f8e3e0] text-px-bad',
}

export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[13px] font-medium ${toneBox[tone]}`}>{children}</span>
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[15px] font-medium">{label}</span>
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
        <div className="fixed inset-x-4 bottom-20 z-50 mx-auto max-w-md md:bottom-6" aria-live="polite">
          <p className={`fade-in rounded-lg px-4 py-3 text-[15px] text-white shadow-lg ${message.bad ? 'bg-px-bad' : 'bg-px-ink'}`}>{message.text}</p>
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
