/** "today", "yesterday", "3 days ago": how long ago a visit was prepared, for people. */
export function preparedAgo (preparedAt: string, now: number = Date.now()): string {
  const days = Math.floor((now - Date.parse(preparedAt)) / 86_400_000)
  if (days < 1) {
    return 'today'
  }
  return days === 1 ? 'yesterday' : `${days} days ago`
}
