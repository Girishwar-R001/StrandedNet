export default function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
      <rect width="32" height="32" rx="8" fill="#006194" />
      <path d="M6 22h7l6-12h7" fill="none" stroke="#93ccff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="6" cy="22" r="2.6" fill="#fff" />
      <circle cx="26" cy="10" r="2.6" fill="#fff" />
    </svg>
  )
}
