export function when(iso: string): string {
  const at = new Date(iso).getTime()
  const seconds = Math.max(0, (Date.now() - at) / 1000)
  if (seconds < 60) return 'now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (new Date(at).toDateString() === new Date().toDateString()) return `${Math.floor(seconds / 3600)}h`
  if (seconds < 6 * 86400) return new Date(at).toLocaleDateString([], { weekday: 'short' })
  return new Date(at).toLocaleDateString([], { month: 'short', day: 'numeric' })
}
