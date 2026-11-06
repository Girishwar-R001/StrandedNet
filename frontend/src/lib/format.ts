export const hhmm = (m: number | null | undefined) => {
  if (m === null || m === undefined) return '–'
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

export const parseHhmm = (text: string) => {
  const [h, m] = text.split(':').map(Number)
  return h * 60 + m
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

export const titleCase = (text: string) => text.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const REQUIREMENT_LABEL: Record<string, string> = {
  wheelchair: 'Wheelchair',
  step_free: 'Step-free',
  luggage: 'Luggage',
}

export const timeAgo = (iso: string) => {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  return `${Math.floor(seconds / 3600)} h ago`
}
