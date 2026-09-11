<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, nextTick, onActivated, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type NetworkResult } from '../api/client'
import { useScrapeStore } from '../stores/scrape'

const scrape = useScrapeStore()
const results = ref<NetworkResult[]>([])
const running = ref(false)
const netBox = ref<HTMLElement>()
let pollTimer: number | undefined

const logText = computed(() => scrape.netLogs.map((l) => DOMPurify.sanitize(l)).join('\n'))

const tableRows = computed(() =>
  results.value.map((r) => ({
    group: r.spec?.group ?? '',
    name: r.spec?.name ?? '',
    url: r.spec?.url ?? '',
    status: r.status,
    message: r.message,
    elapsed: r.elapsed_ms != null ? `${(r.elapsed_ms / 1000).toFixed(1)}s` : '-',
  })),
)

function statusTag(status: string): 'success' | 'warning' | 'danger' | 'info' {
  const s = status.toLowerCase()
  if (s.includes('ok') || s.includes('pass')) return 'success'
  if (s.includes('warn')) return 'warning'
  if (s.includes('fail') || s.includes('error')) return 'danger'
  return 'info'
}

async function refresh() {
  try {
    const snap = await api.networkResults()
    results.value = snap.results
    running.value = snap.running
    if (snap.running && !pollTimer) {
      pollTimer = window.setInterval(async () => {
        const s = await api.networkResults()
        results.value = s.results
        running.value = s.running
        if (!s.running) {
          clearInterval(pollTimer)
          pollTimer = undefined
        }
      }, 1500)
    }
  } catch {
    /* ignore */
  }
}

async function start(retryFailedOnly: boolean) {
  try {
    await api.networkCheck(retryFailedOnly)
    ElMessage.success('检测已开始')
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function stop() {
  await api.networkStop()
  ElMessage.info('停止请求已发送')
}

function copyReport() {
  const lines = results.value.map(
    (r) =>
      `[${r.status}] ${r.spec?.group ?? ''} / ${r.spec?.name ?? ''} (${r.spec?.url ?? ''}) ${r.message}${
        r.error ? ` | ${r.error}` : ''
      }${r.elapsed_ms != null ? ` ${(r.elapsed_ms / 1000).toFixed(1)}s` : ''}`,
  )
  navigator.clipboard
    .writeText(lines.join('\n'))
    .then(() => ElMessage.success('诊断报告已复制'))
    .catch(() => ElMessage.error('复制失败'))
}

watch(
  () => scrape.netLogs.length,
  async () => {
    await nextTick()
    if (netBox.value) netBox.value.scrollTop = netBox.value.scrollHeight
  },
)

onActivated(refresh)
</script>

<template>
  <div class="net-view">
    <el-card shadow="never" class="actions">
      <el-button type="primary" :disabled="running" @click="start(false)">开始检测</el-button>
      <el-button :disabled="running" @click="start(true)">仅重测失败项</el-button>
      <el-button type="danger" :disabled="!running" @click="stop">停止</el-button>
      <el-button :disabled="!results.length" @click="copyReport">复制诊断报告</el-button>
      <el-tag v-if="running" type="warning" size="small" class="ml">检测中…</el-tag>
    </el-card>

    <el-tabs>
      <el-tab-pane label="结果列表" name="table">
        <el-table :data="tableRows" size="small" height="380px" border>
          <el-table-column prop="group" label="分组" width="130" />
          <el-table-column prop="name" label="检测项" width="180" />
          <el-table-column prop="url" label="地址" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="信息" min-width="200" show-overflow-tooltip />
          <el-table-column prop="elapsed" label="耗时" width="80" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="检测日志" name="log">
        <pre ref="netBox" class="log-box">{{ logText || '（点击「开始检测」运行…）' }}</pre>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.net-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.actions :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 16px;
}
.ml {
  margin-left: 8px;
}
.log-box {
  margin: 0;
  padding: 12px;
  height: 380px;
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.7;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
