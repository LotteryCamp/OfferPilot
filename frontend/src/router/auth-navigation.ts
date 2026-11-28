import { isMatterId } from './paths'

export function safeReturnPath(input: unknown): string {
  if (typeof input !== 'string' || !input.startsWith('/') || input.startsWith('//'))
    return '/matters'
  try {
    const base = 'https://offerpilot.invalid'
    const url = new URL(input, base)
    if (url.origin !== base) return '/matters'
    const parts = url.pathname.split('/')
    const isWorkspace =
      parts[1] === 'matters' &&
      isMatterId(parts[2]) &&
      (parts.length === 3 ||
        (parts.length === 4 && ['overview', 'sources', 'plan', 'tasks'].includes(parts[3])))
    if (['/matters', '/matters/new', '/account'].includes(url.pathname) || isWorkspace) {
      return url.pathname + url.search + url.hash
    }
  } catch {
    return '/matters'
  }
  return '/matters'
}
