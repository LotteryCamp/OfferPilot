<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElCheckbox, ElEmpty, ElSkeleton, ElTag } from 'element-plus'
import { isMatterId } from '../../router/paths'
import type { Matter } from '../matters/types'
import { displayDate, normalizeMatterId, safeSourceUrl, statusLabel } from '../sources/presentation'
import { usePlanReview } from './usePlanReview'
import { canConfirmBasis } from './contracts'
import { selfCheckLabel, selfCheckTone } from '../sources/selfCheck'

const props = defineProps<{ matterId: string; matter: Matter }>()
const emit = defineEmits<{ changed: [] }>()
const route = useRoute()
const router = useRouter()
const matterId = computed(() => normalizeMatterId(props.matterId))
const linkedPlanId = computed(() => {
  const value = route.query.plan
  if (value === undefined) return undefined
  return isMatterId(value) ? value.toLowerCase() : ''
})
const review = usePlanReview(() => emit('changed'))
const {
  plans,
  plan,
  tasks,
  selectedId,
  loading,
  submitting,
  error,
  taskError,
  decisionError,
  notice,
  reviewed,
  attempt,
  refreshRequired,
} = review
watch(
  [matterId, linkedPlanId],
  ([id, planId]) => {
    if (id) void review.load(id, planId)
    else review.reset()
  },
  { immediate: true },
)
const canDecide = computed(
  () =>
    plan.value?.status === 'pending' &&
    reviewed.value &&
    !loading.value &&
    !submitting.value &&
    !refreshRequired.value,
)
const items = computed(() => [...(plan.value?.items ?? [])].sort((a, b) => a.seq - b.seq))
const staleBasis = computed(() => !!plan.value && !canConfirmBasis(plan.value))
function reload() {
  if (matterId.value && !submitting.value) void review.load(matterId.value, linkedPlanId.value)
}
function selectVersion(planId: string) {
  void router.replace({ query: { ...route.query, plan: planId } })
}
function itemName(id: string) {
  return plan.value?.items.find((item) => item.id === id)?.title ?? `条目标识 ${id}`
}
</script>

<template>
  <section v-if="!matterId || matterId !== matter.id" class="card">
    <h2>事项标识无效</h2>
    <RouterLink to="/matters">返回事项工作台</RouterLink>
  </section>
  <div v-else class="business-module plan-page" data-testid="plan-page">
    <div class="page-heading">
      <div>
        <h2>审阅候选计划</h2>
        <p class="muted">核对范围、任务性质、时间与来源依据。</p>
      </div>
      <ElButton data-testid="plan-refresh" :loading="loading" :disabled="submitting" @click="reload"
        >重新读取</ElButton
      >
    </div>
    <ElAlert
      v-if="plan?.status === 'pending'"
      type="info"
      :closable="false"
      title="候选计划等待你的决定。确认后创建个人任务；拒绝不会创建任务。"
    />
    <ElAlert v-if="notice" type="info" :closable="false" :title="notice" role="status" />
    <ElAlert
      v-if="decisionError && !plan"
      type="error"
      :closable="false"
      :title="decisionError"
      role="alert"
    />
    <div v-if="error" role="alert" class="read-error panel">
      <p>{{ error }}</p>
      <ElButton :disabled="submitting" @click="reload">重试读取</ElButton>
    </div>
    <ElSkeleton v-if="loading && !plan" :rows="6" animated class="panel loading-panel" />
    <section v-if="!loading && !error && !plans.length" class="panel loading-panel">
      <ElEmpty description="当前事项暂无候选计划"
        ><p class="muted">Agent 生成并保存候选计划后，可在此审阅。</p></ElEmpty
      >
    </section>
    <div v-if="plans.length" class="plan-version-bar">
      <label for="plan-version">计划版本</label>
      <select
        id="plan-version"
        :value="selectedId"
        :disabled="submitting || loading"
        @change="selectVersion(($event.target as HTMLSelectElement).value)"
      >
        <option v-if="!selectedId" disabled value="">选择计划版本</option>
        <option v-for="entry in plans" :key="entry.id" :value="entry.id">
          v{{ entry.version_no }} · {{ statusLabel('plan', entry.status) }} ·
          {{ displayDate(entry.generated_at) }}
        </option>
      </select>
    </div>
    <section v-if="plan" class="panel plan-summary">
      <div class="section-heading">
        <h2>候选计划 v{{ plan.version_no }}</h2>
        <ElTag type="info">{{ statusLabel('plan', plan.status) }}</ElTag>
      </div>
      <p v-if="plan.status === 'pending'" class="plan-impact">
        本候选包含 {{ items.length }} 个条目。确认后创建个人任务；拒绝后保留原有任务。
        <a href="#plan-decision" class="secondary-link">前往计划决定</a>
      </p>
      <p class="muted">
        适用年度：{{ plan.matter.scope_year ?? '未填写' }} · 生成于
        {{ displayDate(plan.generated_at) }}
      </p>
      <p v-if="plan.status === 'expired'" class="error-text">
        计划已过期，请重新生成并审阅候选计划。
      </p>
      <RouterLink
        v-if="plan.status === 'expired' || staleBasis"
        :to="{ name: 'matter-sources', params: { matterId } }"
        class="secondary-link"
        data-testid="plan-regenerate"
        >返回来源与条件重新分析 →</RouterLink
      >
      <ElAlert
        v-if="plan.status === 'pending' && staleBasis"
        data-testid="plan-stale-basis"
        type="warning"
        :closable="false"
        title="个人信息依据已变化，此候选不能继续确认。请返回来源与条件重新分析，再审阅新候选；也可拒绝此候选。"
      />
      <ul v-if="plan.stale_facts?.length" class="muted">
        <li v-for="fact in plan.stale_facts" :key="fact.fact_type">
          {{ fact.fact_type === 'gpa.rank' ? '成绩排名' : fact.fact_type }}：生成时
          {{ fact.stored_version_no === null ? '未提供' : `v${fact.stored_version_no}` }}，当前
          {{ fact.current_version_no === null ? '未提供' : `v${fact.current_version_no}` }}
        </li>
      </ul>
      <p v-if="plan.decision" class="muted">
        决定：{{ statusLabel('plan', plan.decision.decision) }} ·
        {{ displayDate(plan.decision.decided_at) }}
      </p>
      <details>
        <summary>查看生成依据标识</summary>
        <p class="muted break-text">{{ plan.basis_version }}</p>
      </details>
    </section>

    <div v-if="plans.length" class="plan-layout">
      <div v-if="plan" class="source-content">
        <section class="panel">
          <h2>候选条目 · {{ items.length }} 项</h2>
          <ElEmpty v-if="!items.length" description="暂无候选条目" />
          <article v-for="item in items" :key="item.id" class="requirement-card">
            <h3>{{ item.seq }}. {{ item.title }}</h3>
            <ElTag
              :type="item.obligation_nature === 'required' ? 'warning' : 'info'"
              effect="light"
              >{{ statusLabel('obligation', item.obligation_nature) }}</ElTag
            >
            <p>{{ item.detail || '未提供补充说明' }}</p>
            <dl class="metadata-grid">
              <div>
                <dt>官方截止</dt>
                <dd>{{ displayDate(item.official_deadline_at || item.official_deadline_date) }}</dd>
              </div>
              <div>
                <dt>建议准备日</dt>
                <dd>{{ displayDate(item.suggested_date) }}</dd>
              </div>
              <div class="wide">
                <dt>前置条目</dt>
                <dd>
                  {{
                    item.depends_on_item_ids.length
                      ? item.depends_on_item_ids.map(itemName).join('；')
                      : '无前置条目'
                  }}
                </dd>
              </div>
              <div>
                <dt>完成证据</dt>
                <dd>{{ item.evidence_required ? '需要提供' : '未要求' }}</dd>
              </div>
              <div v-if="item.requirement">
                <dt>关联要求</dt>
                <dd>
                  {{ item.requirement.label }} ·
                  {{ statusLabel('extraction', item.requirement.extract_status) }}
                </dd>
              </div>
            </dl>
            <section
              v-if="item.requirement"
              class="evidence-block"
              data-testid="plan-item-self-check"
            >
              <h4>关联要求的自查结果</h4>
              <template v-if="item.requirement.self_check">
                <ElTag :type="selfCheckTone(item.requirement.self_check.conclusion)">{{
                  selfCheckLabel(item.requirement.self_check.conclusion)
                }}</ElTag>
                <p>{{ item.requirement.self_check.reason }}</p>
                <p v-if="item.requirement.self_check.missing_fields.length" class="muted">
                  待补充或核对：{{ item.requirement.self_check.missing_fields.join('、') }}
                </p>
                <ul v-if="item.requirement.self_check.gaps.length">
                  <li v-for="(gap, index) in item.requirement.self_check.gaps" :key="index">
                    {{ gap.description }}{{ gap.locator ? `（${gap.locator}）` : '' }}
                  </li>
                </ul>
              </template>
              <p v-else class="muted">尚无可读取的自查结果，请返回来源与条件核对。</p>
            </section>
            <p v-if="!item.sources.length" class="error-text">
              此条目未提供出处，采用前请核对依据。
            </p>
            <details v-if="item.sources.length" class="requirement-evidence">
              <summary>查看原文依据 · {{ item.sources.length }} 处</summary>
              <div
                v-for="(source, index) in item.sources"
                :key="`${source.snapshot_id}/${index}`"
                class="evidence-block"
              >
                <strong>{{ source.publisher }} · {{ source.locator }}</strong>
                <blockquote>{{ source.quote || '未提供引文，请查看原文。' }}</blockquote>
                <p>
                  {{ statusLabel('lifecycle', source.source_status) }} · 快照 v{{
                    source.version_no
                  }}
                  · {{ source.is_current ? '当前版本' : '历史版本' }}
                </p>
                <p class="muted">获取于 {{ displayDate(source.fetched_at) }}</p>
                <a
                  v-if="safeSourceUrl(source.url)"
                  :href="safeSourceUrl(source.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  >打开原网页 ↗</a
                >
                <p v-else class="error-text">来源链接不可打开</p>
              </div>
            </details>
          </article>
        </section>
        <section
          v-if="plan.status === 'confirmed'"
          class="panel"
          data-testid="plan-tasks"
          :data-plan-id="plan.id"
        >
          <div class="section-heading">
            <h2>本计划的个人任务</h2>
            <div class="module-actions">
              <RouterLink
                :to="{ name: 'matter-tasks', params: { matterId } }"
                class="secondary-link"
                >查看全部正式任务 →</RouterLink
              >
              <ElButton :disabled="submitting" :loading="loading" @click="reload"
                >刷新任务</ElButton
              >
            </div>
          </div>
          <p v-if="taskError" role="alert" class="error-text">
            决定已记录，任务列表读取未完成：{{ taskError }}
          </p>
          <p v-else-if="!tasks.length && !loading" class="muted">
            读取结果暂无本计划任务，请刷新核对。
          </p>
          <article v-for="task in tasks" :key="task.id" class="requirement-card">
            <h3>{{ task.title }}</h3>
            <ElTag type="info">{{ statusLabel('task', task.status) }}</ElTag>
            <p class="muted">
              官方截止：{{
                displayDate(task.official_deadline_at || task.official_deadline_date)
              }}
              · 建议准备日：{{ displayDate(task.suggested_date) }}
            </p>
            <details v-if="task.sources.length">
              <summary>查看任务来源依据</summary>
              <div v-for="(source, index) in task.sources" :key="index" class="evidence-block">
                <strong
                  >{{ source.publisher }} · {{ source.locator }} · 快照 v{{
                    source.version_no
                  }}</strong
                >
                <blockquote>{{ source.quote || '未提供引文，请查看原文。' }}</blockquote>
                <a
                  v-if="safeSourceUrl(source.url)"
                  :href="safeSourceUrl(source.url)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  >打开原网页 ↗</a
                >
              </div>
            </details>
          </article>
        </section>
      </div>
      <aside v-if="plan" class="source-content">
        <section
          id="plan-decision"
          class="panel decision-panel"
          aria-label="计划决定"
          data-testid="plan-decision"
          :data-plan-id="plan.id"
          :data-plan-status="plan.status"
        >
          <h2>你的决定</h2>
          <p v-if="decisionError" role="alert" class="error-text">{{ decisionError }}</p>
          <template v-if="plan.status === 'pending'">
            <ElAlert
              v-if="attempt"
              type="warning"
              :closable="false"
              title="上次操作结果尚未确定。请重新读取状态，或使用原操作标识重试；当前不能改做相反决定。"
            />
            <p>确认采用后，系统会把候选条目创建为个人任务；对外提交仍需你自行完成。</p>
            <ElCheckbox v-model="reviewed" :disabled="submitting || loading"
              >我已核对计划条目、官方截止与来源依据</ElCheckbox
            >
            <div class="decision-buttons">
              <ElButton
                data-testid="plan-confirm"
                type="primary"
                :loading="submitting && (!attempt || attempt.action === 'confirm')"
                :disabled="!canDecide || staleBasis || (!!attempt && attempt.action !== 'confirm')"
                @click="review.decide('confirm')"
                >{{ attempt?.action === 'confirm' ? '重试确认' : '确认采用并创建任务' }}</ElButton
              >
              <ElButton
                data-testid="plan-reject"
                :loading="submitting && attempt?.action === 'reject'"
                :disabled="!canDecide || (!!attempt && attempt.action !== 'reject')"
                @click="review.decide('reject')"
                >{{ attempt?.action === 'reject' ? '重试拒绝' : '拒绝此候选计划' }}</ElButton
              >
            </div>
            <p v-if="refreshRequired" class="muted">请先重新读取计划，再作决定。</p>
          </template>
          <p v-else-if="plan.status === 'rejected'">该候选计划已拒绝，拒绝决定不会创建任务。</p>
          <p v-else-if="plan.status === 'confirmed'">
            该计划已确认，可查看下方重新读取的个人任务。
          </p>
          <p v-else-if="plan.status !== 'confirmed'" class="muted">
            当前状态不可作确认或拒绝决定。
          </p>
        </section>
        <section class="panel">
          <h2>核对来源</h2>
          <p class="muted">采用前请回看通知原文，核对年度、适用对象及截止时间。</p>
          <RouterLink :to="{ name: 'matter-sources', params: { matterId } }" class="secondary-link"
            >查看来源与条件 →</RouterLink
          >
        </section>
      </aside>
    </div>
  </div>
</template>
