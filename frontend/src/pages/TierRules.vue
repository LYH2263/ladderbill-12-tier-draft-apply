<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON, putJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const active = ref([])
const draftItems = ref(null)
const rows = ref([])
const kwh = ref(400)
const peak = ref(false)
const trial = ref(null)
const preview = ref(null)
const applied = ref(null)
const consistency = ref(null)
const error = ref('')
const busy = ref(false)

const dirtyHint = ref('')

function toEditor(items) {
  return items.map(t => ({ up_to: t.up_to ?? '', price: t.price }))
}
function fromEditor() {
  return rows.value.map(r => ({ up_to: r.up_to === '' || r.up_to === null ? null : Number(r.up_to), price: Number(r.price) }))
}

async function refresh() {
  const d = await getJSON('/api/tiers/draft')
  active.value = d.active
  draftItems.value = d.items
  rows.value = toEditor(d.items ?? d.active)
  dirtyHint.value = d.items ? '' : '草稿尚未保存，编辑器已按当前正式档预填'
}

function addRow() {
  rows.value.push({ up_to: '', price: 0 })
}
function removeRow(i) {
  rows.value.splice(i, 1)
}

async function saveDraft() {
  error.value = ''
  const items = fromEditor()
  const saved = await putJSON('/api/tiers/draft', { tiers: items })
  draftItems.value = saved.items
  rows.value = toEditor(saved.items)
  dirtyHint.value = '草稿已保存（尚未生效）'
}

async function withBusy(fn) {
  busy.value = true
  error.value = ''
  try {
    // trial / preview / apply always run against the saved draft, so persist first
    await saveDraft()
    await fn()
  } catch (e) {
    error.value = extractDetail(e)
  } finally {
    busy.value = false
  }
}

function extractDetail(e) {
  try { return JSON.parse(e.message).detail ?? e.message } catch { return e.message }
}

async function runTrial() {
  await withBusy(async () => {
    trial.value = await postJSON('/api/tiers/draft/trial', { kwh: kwh.value, peak: peak.value })
    preview.value = null
    applied.value = null
    consistency.value = null
  })
}

async function runPreview() {
  await withBusy(async () => {
    preview.value = await postJSON('/api/tiers/draft/preview', { kwh: kwh.value, peak: peak.value })
    applied.value = null
    consistency.value = null
  })
}

async function runApply() {
  await withBusy(async () => {
    const summary = await postJSON('/api/tiers/draft/apply', { kwh: kwh.value, peak: peak.value })
    applied.value = summary
    preview.value = null
    trial.value = null
    await refresh()

    // Acceptance check: what the workbench now reads from the ACTIVE ladder
    // must equal the post-apply summary, segment by segment.
    const wb = await postJSON('/api/bill', { kwh: kwh.value, peak: peak.value, persist: false })
    consistency.value = {
      wb,
      match:
        JSON.stringify(wb.segments) === JSON.stringify(summary.after.segments) &&
        wb.total === summary.after.total,
    }
  })
}

onMounted(refresh)
</script>

<template>
  <div class="page rules">
    <h1>阶梯单价 · 草稿</h1>

    <div class="rules-grid">
      <section class="panel">
        <h3>草稿编辑（未生效）</h3>
        <p class="muted" v-if="dirtyHint">{{ dirtyHint }}</p>
        <table>
          <thead><tr><th>顺序</th><th>上限(kWh)</th><th>单价(元)</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="i">
              <td>{{ i + 1 }}</td>
              <td><input type="number" v-model="r.up_to" min="0" step="1" placeholder="末档留空=开口" /></td>
              <td><input type="number" v-model.number="r.price" min="0" step="0.01" /></td>
              <td><button class="ghost" @click="removeRow(i)" :disabled="rows.length <= 1">删</button></td>
            </tr>
          </tbody>
        </table>
        <div class="btn-row">
          <button class="ghost" @click="addRow">加一档</button>
          <button @click="saveDraft" :disabled="busy">保存草稿</button>
        </div>
        <p class="muted small">校验在试算/应用时进行：上限须严格单调递增，仅末档可为开口；单价须非负。</p>
      </section>

      <section class="panel">
        <h3>正式档（当前生效，只读）</h3>
        <table>
          <thead><tr><th>顺序</th><th>上限(kWh)</th><th>单价(元)</th></tr></thead>
          <tbody>
            <tr v-for="(t, i) in active" :key="i">
              <td>{{ i + 1 }}</td>
              <td>{{ t.up_to ?? '以上' }}</td>
              <td>{{ t.price }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <section class="panel">
      <h3>探针电量试算（草稿来源，不入运行记录）</h3>
      <div class="form-row">
        <label>电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" /></label>
        <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
        <button @click="runTrial" :disabled="busy">草稿试算</button>
        <button class="ghost" @click="runPreview" :disabled="busy">应用前对比</button>
      </div>
      <p v-if="error" class="err">✗ {{ error }}</p>
      <div v-if="trial" class="trial-box">
        <div class="src-tag draft-tag">source = draft（试算）</div>
        <p>合计 ¥{{ trial.total }}（尖峰系数 ×{{ trial.peak_factor }}）</p>
        <SegmentTable :rows="trial.segments" />
      </div>
    </section>

    <section v-if="preview" class="panel">
      <h3>应用对比摘要（应用前预览，尚未替换正式档）</h3>
      <div class="compare-grid">
        <div>
          <h4 class="muted">应用前 · 正式档</h4>
          <p class="hero-num small-hero">¥{{ preview.before.total }}</p>
          <SegmentTable :rows="preview.before.segments" />
        </div>
        <div>
          <h4 class="muted">应用后 · 草稿档</h4>
          <p class="hero-num small-hero">¥{{ preview.after.total }}</p>
          <SegmentTable :rows="preview.after.segments" />
        </div>
      </div>
      <p>合计差额：
        <strong :class="preview.after.total - preview.before.total > 0 ? 'up' : 'down'">
          {{ (preview.after.total - preview.before.total) >= 0 ? '+' : '' }}{{ (preview.after.total - preview.before.total).toFixed(2) }} 元
        </strong>
      </p>
      <button @click="runApply" :disabled="busy">确认原子应用（替换正式档）</button>
    </section>

    <section v-if="applied" class="panel">
      <h3>应用结果</h3>
      <p class="ok">✓ 草稿已通过校验并原子替换正式档（同电量 {{ applied.kwh }} kWh）</p>
      <div class="compare-grid">
        <div>
          <h4 class="muted">应用前</h4>
          <p class="hero-num small-hero">¥{{ applied.before.total }}</p>
          <SegmentTable :rows="applied.before.segments" />
        </div>
        <div>
          <h4 class="muted">应用后摘要</h4>
          <p class="hero-num small-hero">¥{{ applied.after.total }}</p>
          <SegmentTable :rows="applied.after.segments" />
        </div>
      </div>
      <div v-if="consistency" class="verify">
        <p v-if="consistency.match" class="ok">✓ 已用测算台接口（/api/bill，读正式档、未入库）复核：分段与合计与应用后摘要完全一致（¥{{ consistency.wb.total }}）</p>
        <p v-else class="err">✗ 测算台正式档分段与应用后摘要不一致，请检查</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.rules-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
.form-row, .btn-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: end; margin: 0.5rem 0; }
input[type=number] { width: 7rem; }
.ghost { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
.small { font-size: 0.8rem; }
.small-hero { font-size: 1.8rem; margin: 0.25rem 0 0.5rem; }
.src-tag { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 6px; font-size: 0.8rem; margin-bottom: 0.4rem; }
.draft-tag { background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
.err { color: #ff7b72; }
.ok { color: var(--accent); }
.up { color: #ff9d5c; }
.down { color: #5cd6a0; }
.verify { margin-top: 0.75rem; padding-top: 0.6rem; border-top: 1px solid color-mix(in srgb, var(--muted) 35%, transparent); }
</style>
