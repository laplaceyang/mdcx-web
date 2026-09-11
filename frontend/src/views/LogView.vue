<script setup lang="ts">
import DOMPurify from 'dompurify'
import { nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useScrapeStore } from '../stores/scrape'

const scrape = useScrapeStore()
const activePane = ref<'main' | 'detail' | 'failed' | 'net'>('main')
const mainBox = ref<HTMLElement>()
const detailBox = ref<HTMLElement>()
const failedBox = ref<HTMLElement>()
const netBox = ref<HTMLElement>()

function sanitized(lines: string[]): string {
  return lines.map((l) => DOMPurify.sanitize(l)).join('\n')
}

function autoScroll(box?: HTMLElement) {
  if (box) box.scrollTop = box.scrollHeight
}

watch(
  () => scrape.mainLogs.length,
  async () => {
    await nextTick()
    autoScroll(mainBox.value)
  },
)
watch(
  () => scrape.failedLogs.length,
  async () => {
    await nextTick()
    autoScroll(failedBox.value)
  },
)
watch(
  () => scrape.netLogs.length,
  async () => {
    await nextTick()
    autoScroll(netBox.value)
  },
)
watch(
  () => scrape.detailLogText.length,
  async () => {
    await nextTick()
    autoScroll(detailBox.value)
  },
)

async function onRetryFailed() {
  try {
    await api.retryFailed()
    ElMessage.success('已开始重刮失败列表')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

function saveFailedList() {
  const items = scrape.results.filter((r) => r.status === 'fail')
  const lines = items.map((r) => String(r.show?.file_info?.file_path ?? ''))
  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'failed.txt'
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<template>
  <div class="log-view">
    <el-card shadow="never" class="actions">
      <el-button type="danger" :disabled="!scrape.running" @click="() => api.scrapeStop()">停止</el-button>
      <el-button type="primary" :disabled="scrape.running || scrape.stopping" @click="onRetryFailed">
        重刮失败列表
      </el-button>
      <el-button @click="saveFailedList">保存失败列表</el-button>
      <span class="hint">主日志 / 详情日志 / 失败面板 实时推送</span>
    </el-card>

    <el-tabs v-model="activePane" class="panes">
      <el-tab-pane label="主日志" name="main">
        <pre ref="mainBox" class="log-box html-log" v-html="sanitized(scrape.mainLogs)"></pre>
      </el-tab-pane>
      <el-tab-pane label="详情日志" name="detail">
        <pre ref="detailBox" class="log-box plain">{{ scrape.detailLogText || '（等待刮削输出…）' }}</pre>
      </el-tab-pane>
      <el-tab-pane label="失败面板" name="failed">
        <pre ref="failedBox" class="log-box html-log" v-html="sanitized(scrape.failedLogs)"></pre>
      </el-tab-pane>
      <el-tab-pane label="网络检测" name="net">
        <pre ref="netBox" class="log-box html-log" v-html="sanitized(scrape.netLogs)"></pre>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.log-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.actions :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 16px;
}
.hint {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.log-box {
  margin: 0;
  padding: 12px;
  height: calc(100vh - 250px);
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.7;
  border-radius: 6px;
}
.log-box.html-log {
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
</style>
