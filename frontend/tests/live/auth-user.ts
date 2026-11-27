import { randomUUID } from 'node:crypto'
import { expect, type APIRequestContext } from '@playwright/test'

export function createTestCredentials() {
  const unique = randomUUID()
  return {
    email: `qa-${unique}@example.com`,
    display_name: `联调用户 ${unique.slice(0, 8)}`,
    password: `test-${randomUUID()}`,
  }
}

export async function registerTestUser(
  request: APIRequestContext,
  credentials = createTestCredentials(),
) {
  const response = await request.post('/api/v1/auth/register', { data: credentials })
  expect(response.status()).toBe(201)
  const account = await response.json()
  expect(account.user).toMatchObject({ email: credentials.email, account_type: 'applicant' })
  expect(account.session.remember).toBe(false)
  return account
}
