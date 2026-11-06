import { Car, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { pxApi, useLive } from '../lib/api'
import { hhmm } from '../lib/format'

/** Counts only: the API sends no names, references or exact locations. */
export default function SurgeBanner({ offerLink = true }: { offerLink?: boolean }) {
  const { data } = useLive(pxApi, '/me/surge')
  if (!data?.active) return null
  return (
    <section className="rounded-2xl bg-px-warn-soft p-5" aria-label="Surge Carpool Mobilisation">
      <h2 className="flex items-center gap-2 text-lg font-semibold text-px-warn"><TriangleAlert size={19} /> Surge Carpool Mobilisation</h2>
      <p className="mt-1 text-[15px]">{data.pooled} stranded passengers are pooled across {data.corridors.length} corridors. If you're heading this way, a spare seat makes a real difference.</p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {data.corridors.map((c: any) => (
          <li key={c.label} className="flex items-center justify-between gap-3 rounded-xl bg-px-card px-3 py-2">
            <span className="min-w-0">
              <span className="block truncate text-[15px] font-semibold">{c.name}</span>
              <span className="num block text-sm text-px-muted">{hhmm(c.window_start)}–{hhmm(c.window_end)}</span>
            </span>
            <span className="num shrink-0 font-display text-xl font-bold">{c.passengers}</span>
          </li>
        ))}
      </ul>
      {offerLink && (
        <Link to="/app/carpool" className="mt-3 inline-flex min-h-11 items-center gap-2 font-semibold text-px-accent underline underline-offset-2">
          <Car size={18} /> Offer a spare seat
        </Link>
      )}
    </section>
  )
}
