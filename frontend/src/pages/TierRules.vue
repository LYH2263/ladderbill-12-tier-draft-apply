<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON, putJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const official = ref([])
const draftRows = ref([])
const draftUpdatedAt = ref(null)
const hasDraft = ref(false)
const kwh = ref(220)
const peak = ref(false)
const sim = ref(null)
const applied = ref(null)
const error = ref('')
const notice = ref('')

const errMsg = (e) => {
  try { return JSON.parse(e.message).detail ?? e.message } catch { return e.message }
}
const fmtDelta = (d) => (d > 0 ? `+${d}` : `${d}`)

const load = async () => {
  official.value = (await getJSON('/api/tiers')).items
  const d = await getJSON('/api/tiers/draft')
  draftUpdatedAt.value = d.updated_at
  hasDraft.value = d.items.length > 0
  const src = d.items.length ? d.items : official.value
  draftRows.value = src.map((t) => ({ up_to: t.up_to, price: t.price }))
}

const copyOfficial = () => {
  draftRows.value = official.value.map((t) => ({ up_to: t.up_to, price: t.price }))
}
const addRow = () => draftRows.value.push({ up_to: null, price: 0 })
const removeRow = (i) => draftRows.value.splice(i, 1)

const saveDraft = async () => {
  error.value = ''; notice.value = ''; sim.value = null; applied.value = null
  try {
    const d = await putJSON('/api/tiers/draft', { items: draftRows.value })
    hasDraft.value = d.items.length > 0
    draftUpdatedAt.value = d.updated_at
    notice.value = '草稿已保存（未生效）'
  } catch (e) { error.value = errMsg(e) }
}

const simulate = async () => {
  error.value = ''; notice.value = ''; applied.value = null
  try {
    sim.value = await postJSON('/api/tiers/draft/simulate', { kwh: kwh.value, peak: peak.value })
  } catch (e) { error.value = errMsg(e); sim.value = null }
}

const apply = async () => {
  error.value = ''; notice.value = ''
  try {
    applied.value = await postJSON('/api/tiers/apply', { kwh: kwh.value, peak: peak.value })
    official.value = applied.value.tiers
    sim.value = null
    notice.value = '草稿已应用为正式档，测算台将按新档计算'
  } catch (e) { error.value = errMsg(e) }
}

onMounted(load)
</script>
<template>
  <div class="page">
    <h1>阶梯单价</h1>
    <p v-if="error" class="panel err">{{ error }}</p>
    <p v-if="notice" class="panel ok">{{ notice }}</p>

    <div class="panel">
      <h2>正式档（生效中）</h2>
      <table>
        <thead><tr><th>顺序</th><th>上限(kWh)</th><th>单价(元)</th></tr></thead>
        <tbody>
          <tr v-for="t in official" :key="t.id">
            <td>{{ t.sort_order }}</td>
            <td>{{ t.up_to ?? '以上' }}</td>
            <td>{{ t.price }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h2>草稿（未生效）<span v-if="draftUpdatedAt" class="muted tag">保存于 {{ draftUpdatedAt }}</span></h2>
      <table>
        <thead><tr><th>顺序</th><th>上限(kWh)</th><th>单价(元)</th><th></th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in draftRows" :key="i">
            <td>{{ i + 1 }}</td>
            <td>
              <input
                type="number" min="0" step="1" placeholder="以上"
                :value="r.up_to ?? ''"
                @input="r.up_to = $event.target.value === '' ? null : Number($event.target.value)"
              />
            </td>
            <td><input type="number" min="0" step="0.01" v-model.number="r.price" /></td>
            <td><button class="ghost" @click="removeRow(i)">删除</button></td>
          </tr>
        </tbody>
      </table>
      <div class="btn-row">
        <button class="ghost" @click="addRow">加一档</button>
        <button class="ghost" @click="copyOfficial">从正式档复制</button>
        <button @click="saveDraft">保存草稿</button>
      </div>
    </div>

    <div class="panel">
      <h2>探针试算</h2>
      <div class="form-row">
        <label>探针电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" /></label>
        <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
        <button @click="simulate" :disabled="!hasDraft">用草稿试算</button>
        <button @click="apply" :disabled="!hasDraft">应用草稿为正式档</button>
      </div>
      <p v-if="!hasDraft" class="muted">尚无已保存的草稿，请先保存草稿。</p>

      <div v-if="sim" class="compare">
        <p class="muted">来源：{{ sim.source === 'draft' ? '草稿（未生效，不写正式档/不入库）' : sim.source }} · 探针 {{ sim.kwh }} kWh</p>
        <div class="cols">
          <div>
            <h3>草稿试算 ¥{{ sim.draft.total }}</h3>
            <SegmentTable :rows="sim.draft.segments" />
          </div>
          <div>
            <h3>当前正式档 ¥{{ sim.official.total }}</h3>
            <SegmentTable :rows="sim.official.segments" />
          </div>
        </div>
        <p>差额（草稿 − 正式）：<strong :class="{ up: sim.delta_total > 0, down: sim.delta_total < 0 }">{{ fmtDelta(sim.delta_total) }}</strong> 元</p>
      </div>

      <div v-if="applied" class="compare">
        <p class="muted">应用前后对比 · 探针 {{ applied.kwh }} kWh</p>
        <div class="cols">
          <div>
            <h3>应用前（旧正式档）¥{{ applied.before.total }}</h3>
            <SegmentTable :rows="applied.before.segments" />
          </div>
          <div>
            <h3>应用后（新正式档）¥{{ applied.after.total }}</h3>
            <SegmentTable :rows="applied.after.segments" />
          </div>
        </div>
        <p>差额（后 − 前）：<strong :class="{ up: applied.delta_total > 0, down: applied.delta_total < 0 }">{{ fmtDelta(applied.delta_total) }}</strong> 元</p>
      </div>
    </div>
  </div>
</template>
<style scoped>
h2 { font-size: 1.05rem; margin-top: 0; }
h3 { font-size: 0.95rem; }
.tag { font-size: 0.8rem; font-weight: 400; margin-left: 0.5rem; }
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin-bottom: 0.75rem; }
.btn-row { display: flex; gap: 0.6rem; margin-top: 0.75rem; }
input[type=number] { width: 7rem; margin-left: 0.35rem; }
td input { width: 7rem; margin-left: 0; }
.ghost { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
button:disabled { opacity: 0.45; cursor: not-allowed; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.err { color: #ff9d9d; }
.ok { color: var(--accent); }
.up { color: #ff9d9d; }
.down { color: var(--accent); }
</style>
