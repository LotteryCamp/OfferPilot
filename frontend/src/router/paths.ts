const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isMatterId(value: unknown): value is string {
  return typeof value === 'string' && uuidPattern.test(value)
}

export function matterPath(id: string, section = 'overview') {
  if (!isMatterId(id)) throw new Error('事项编号格式无效')
  if (!['overview', 'sources', 'plan', 'tasks'].includes(section)) {
    throw new Error('事项页面无效')
  }
  return `/matters/${encodeURIComponent(id.toLowerCase())}/${section}`
}
