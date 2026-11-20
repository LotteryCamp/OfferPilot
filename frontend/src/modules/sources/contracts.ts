import { z } from 'zod'
import { optionalSelfCheckSchema } from './selfCheck'

const id = z.uuid()
const optionalText = z.string().nullable()
const fragment = z.object({
  locator_kind: z.string(),
  locator: z.string(),
  quote: optionalText,
})
const evidence = fragment.extend({
  id,
  source_id: id,
  snapshot_id: id,
  quote_hash: optionalText,
  fetched_at: optionalText,
})
const requirement = z.object({
  id,
  matter_id: id,
  snapshot_id: id,
  field_key: z.string(),
  label: z.string(),
  obligation_nature: z.string(),
  extract_status: z.string(),
  scope: optionalText,
  value_text: optionalText,
  value_type: z.string(),
  confidence: z.number().min(0).max(1).nullable(),
  checked_at: optionalText,
  evidence: z.array(evidence),
  self_check: optionalSelfCheckSchema,
})
const snapshot = z.object({
  id,
  source_id: id,
  version_no: z.number().int().positive(),
  content_hash: z.string(),
  title: optionalText,
  published_date: optionalText,
  text: optionalText,
  fragments: z.array(fragment),
  fetched_at: optionalText,
  is_current: z.boolean(),
  requirements: z.array(requirement),
})
const source = z.object({
  id,
  publisher: z.string(),
  url: z.string(),
  scope: optionalText,
  scope_year: z.number().int(),
  valid_from: optionalText,
  valid_to: optionalText,
  status: z.string(),
  auto_check_status: z.string(),
  roi_status: z.string(),
  last_fetched_at: optionalText,
  snapshots: z.array(snapshot),
})
export const sourceResponse = z.object({ sources: z.array(source) })
export const sourceReadResponse = z.object({
  source: source.omit({ snapshots: true }),
  snapshot: snapshot.omit({ requirements: true }),
  created: z.object({ source: z.boolean(), snapshot: z.boolean() }),
})
export type SourceReadResult = z.infer<typeof sourceReadResponse>
export const matterResponse = z.object({
  matter: z.object({
    id,
    goal: z.string(),
    scope_year: z.number().int(),
    scope_attrs: z.record(z.string(), z.unknown()),
  }),
})
export type Source = z.infer<typeof source>
export type Snapshot = z.infer<typeof snapshot>
export type Matter = z.infer<typeof matterResponse>['matter']

export function assertMatterBoundary(sources: Source[], matterId: string) {
  for (const item of sources) {
    for (const version of item.snapshots) {
      if (version.source_id !== item.id) throw new Error('来源快照关联不一致，请联系后端核对。')
      for (const rule of version.requirements) {
        if (rule.matter_id !== matterId || rule.snapshot_id !== version.id) {
          throw new Error('要求与当前事项或快照不一致，已停止展示。')
        }
      }
    }
  }
}
