export function agentRunTimeoutMs(seconds?: string) {
  const text = seconds?.trim()
  if (!text) return 420_000
  const value = Number(text)
  if (!Number.isSafeInteger(value) || value <= 0 || value > 2_147_483)
    throw new Error('VITE_AGENT_RUN_TIMEOUT_SECONDS 须为有效的正整数秒数。')
  return value * 1000
}

export function agentRunProxyTimeoutMs(seconds?: string) {
  return Math.min(agentRunTimeoutMs(seconds) + 30_000, 2_147_483_647)
}
