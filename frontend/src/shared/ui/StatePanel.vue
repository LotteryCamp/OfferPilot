<script setup lang="ts">
withDefaults(
  defineProps<{
    kind: 'loading' | 'empty' | 'error' | 'unavailable'
    title: string
    description?: string
    retry?: boolean
  }>(),
  { description: '', retry: false },
)
defineEmits<{ retry: [] }>()
</script>

<template>
  <section
    class="state-panel"
    :class="`state-${kind}`"
    :role="kind === 'error' ? 'alert' : 'status'"
    :aria-busy="kind === 'loading'"
  >
    <span v-if="kind === 'loading'" class="spinner" aria-hidden="true" />
    <span v-else class="state-symbol" aria-hidden="true">{{ kind === 'empty' ? '＋' : 'i' }}</span>
    <h2>{{ title }}</h2>
    <p v-if="description">{{ description }}</p>
    <slot />
    <el-button v-if="retry" @click="$emit('retry')">重新读取</el-button>
  </section>
</template>
