import type { InjectionKey, ShallowRef } from 'vue'
import type { Matter } from './types'

export const currentMatterKey: InjectionKey<{
  matter: ShallowRef<Matter | undefined>
  reload: () => Promise<void>
}> = Symbol('current-matter')
