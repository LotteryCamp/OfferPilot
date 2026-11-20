<script setup lang="ts">
import { ElButton, ElEmpty, ElTag } from 'element-plus'
import type { Snapshot } from './contracts'
import { displayDate, statusLabel } from './presentation'
import { selfCheckLabel, selfCheckTone } from './selfCheck'

defineProps<{ snapshot: Snapshot; availableSnapshots: ReadonlySet<string> }>()
const emit = defineEmits<{ 'open-evidence': [sourceId: string, snapshotId: string] }>()
</script>

<template>
  <section class="panel requirements" data-testid="requirements" :data-snapshot-id="snapshot.id">
    <div class="section-heading">
      <h2>本版本的要求</h2>
      <span class="muted">{{ snapshot.requirements.length }} 条</span>
    </div>
    <ElEmpty v-if="!snapshot.requirements.length" description="已读取，待分析" :image-size="72">
      <p class="muted">此快照尚无关联要求，可先查看原文。</p>
    </ElEmpty>
    <article
      v-for="rule in snapshot.requirements"
      :key="rule.id"
      class="requirement-card"
      data-testid="requirement-card"
      :data-requirement-id="rule.id"
    >
      <h3>{{ rule.label }}</h3>
      <div class="tags">
        <ElTag type="info" effect="plain">{{
          statusLabel('obligation', rule.obligation_nature)
        }}</ElTag>
        <ElTag :type="rule.extract_status === 'to_review' ? 'warning' : 'info'" effect="plain">{{
          statusLabel('extraction', rule.extract_status)
        }}</ElTag>
      </div>
      <p class="requirement-value">{{ rule.value_text || '要求内容待补充' }}</p>
      <p class="muted">适用范围：{{ rule.scope || '未提供，需核对' }}</p>
      <p v-if="rule.checked_at" class="muted">检查时间：{{ displayDate(rule.checked_at) }}</p>
      <section
        v-if="rule.self_check"
        class="self-check"
        data-testid="self-check"
        :data-conclusion="rule.self_check.conclusion"
        :aria-label="`${rule.label}的辅助自查结果`"
      >
        <div class="section-heading">
          <strong>辅助自查</strong>
          <ElTag :type="selfCheckTone(rule.self_check.conclusion)">
            {{ selfCheckLabel(rule.self_check.conclusion) }}
          </ElTag>
        </div>
        <p>{{ rule.self_check.reason }}</p>
        <p v-if="rule.self_check.missing_fields.length" class="muted">
          待补充信息项：{{ rule.self_check.missing_fields.join('、') }}
        </p>
        <p v-if="rule.self_check.computed_deadline_at" class="muted">
          按规则计算的截止时间：{{ displayDate(rule.self_check.computed_deadline_at) }}
        </p>
        <div v-if="rule.self_check.gaps.length" class="self-check-gaps">
          <h4>需要补充或核对的内容</h4>
          <article v-for="(gap, index) in rule.self_check.gaps" :key="index" class="evidence-block">
            <p>{{ gap.description }}</p>
            <p v-if="gap.locator" class="muted">原文位置：{{ gap.locator }}</p>
            <ElButton
              v-if="
                gap.source_id &&
                gap.snapshot_id &&
                availableSnapshots.has(`${gap.source_id}/${gap.snapshot_id}`)
              "
              size="small"
              @click="emit('open-evidence', gap.source_id, gap.snapshot_id)"
              >查看缺口对应快照</ElButton
            >
          </article>
        </div>
      </section>
      <p v-else class="muted">尚无可读取的个人自查结果，请先核对下方来源依据。</p>
      <p v-if="!rule.evidence.length" class="error-text">尚未提供出处定位，需补充后核对。</p>
      <div v-for="entry in rule.evidence" :key="entry.id" class="evidence-block">
        <strong>原文位置 · {{ entry.locator }}</strong>
        <blockquote>{{ entry.quote || '未提供引文，请回看原文。' }}</blockquote>
        <p class="muted break-text">来源 {{ entry.source_id }} / 快照 {{ entry.snapshot_id }}</p>
        <ElButton
          v-if="availableSnapshots.has(`${entry.source_id}/${entry.snapshot_id}`)"
          size="small"
          @click="emit('open-evidence', entry.source_id, entry.snapshot_id)"
          >查看该出处快照</ElButton
        >
        <p v-else class="muted">本列表未返回该出处快照，请按标识核对。</p>
      </div>
    </article>
  </section>
</template>
