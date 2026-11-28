import { z } from 'zod'

export const accountSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  display_name: z.string(),
  account_type: z.enum(['applicant', 'admin']),
  status: z.literal('active'),
  workspace_id: z.uuid(),
  created_at: z.string(),
  updated_at: z.string(),
  deleted_at: z.null(),
})

export const sessionSchema = z.object({
  expires_at: z.iso.datetime({ offset: true }),
  remember: z.boolean(),
})

export const authenticatedAccountSchema = z.object({
  user: accountSchema,
  session: sessionSchema,
})

export type Account = z.infer<typeof accountSchema>
export type Session = z.infer<typeof sessionSchema>
export type AuthenticatedAccount = z.infer<typeof authenticatedAccountSchema>

export interface LoginInput {
  email: string
  password: string
  remember: boolean
}

export interface RegisterInput {
  email: string
  display_name: string
  password: string
}
