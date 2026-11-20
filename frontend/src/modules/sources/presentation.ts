import { z } from 'zod'
import type { Source, Snapshot } from './contracts'

export function normalizeMatterId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const result = z.uuid().safeParse(value.trim())
  return result.success ? result.data.toLowerCase() : null
}

export function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null
    return url.href
  } catch {
    return null
  }
}

export function displayDate(value: string | null): string {
  if (!value) return '未提供'
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return z.iso.date().safeParse(value).success ? value : '时间格式待核对'
  }
  if (!z.iso.datetime({ offset: true }).safeParse(value).success) return '时间格式待核对'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return '时间格式待核对'
  return `${new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(date)}（北京时间）`
}

const labels: Record<string, Record<string, string>> = {
  plan: {
    draft: '草稿',
    pending: '候选 · 待确认',
    confirmed: '已确认',
    rejected: '已拒绝',
    expired: '已过期',
  },
  task: {
    pending: '待开始',
    ready: '可开始',
    in_progress: '进行中',
    blocked: '受阻',
    done: '已完成',
    cancelled: '已取消',
  },
  lifecycle: { active: '可用', withdrawn: '已撤回', invalid: '已失效' },
  check: {
    pending: '待检查',
    passed: '程序检查通过',
    failed: '程序检查失败',
    conflict: '存在冲突',
  },
  extraction: {
    extracted: '已提取',
    checked: '已执行检查',
    to_review: '待核对',
    rejected: '已否决',
  },
  obligation: { required: '必需', advised: '建议', optional: '可选', to_verify: '性质待核对' },
  origin: { original: '原始发布', reposted: '转载', expired: '已过期', ambiguous: '来源存疑' },
}
export function statusLabel(group: string, value: string): string {
  const groupLabels = Object.hasOwn(labels, group) ? labels[group] : undefined
  return groupLabels && Object.hasOwn(groupLabels, value)
    ? groupLabels[value]!
    : `待识别状态（${value}）`
}

export function initialSnapshot(source: Source): Snapshot | undefined {
  return [...source.snapshots].sort(
    (a, b) => Number(b.is_current) - Number(a.is_current) || b.version_no - a.version_no,
  )[0]
}
