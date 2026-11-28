const MAX_TIMER_DELAY = 2_147_000_000
const EXPIRED_RECHECK_DELAY = 10_000

export function createSessionExpiryTimer(
  readExpiry: () => string | undefined,
  recheck: () => Promise<void>,
) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0
  let disposed = false
  let checkedDeadline: number | undefined

  function refresh() {
    clearTimeout(timer)
    const ticket = ++generation
    if (disposed) return
    const deadline = Date.parse(readExpiry() ?? '')
    if (!Number.isFinite(deadline)) return

    function arm() {
      const remaining = deadline - Date.now()
      const delay =
        remaining > 0
          ? Math.min(remaining, MAX_TIMER_DELAY)
          : checkedDeadline === deadline
            ? EXPIRED_RECHECK_DELAY
            : 0
      timer = setTimeout(() => {
        if (ticket !== generation) return
        if (Date.now() < deadline) {
          arm()
          return
        }
        checkedDeadline = deadline
        const scheduleCurrent = () => {
          if (ticket === generation) refresh()
        }
        void recheck().then(scheduleCurrent, scheduleCurrent)
      }, delay)
    }

    arm()
  }

  function dispose() {
    disposed = true
    generation++
    clearTimeout(timer)
  }

  return { refresh, dispose }
}
