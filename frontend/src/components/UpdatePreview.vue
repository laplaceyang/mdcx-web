<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

// 「更新方式」目标路径实时预览：把设置表单当前值交给后端，用真实 render_name 引擎渲染示例
const props = defineProps<{ config: Record<string, any> }>()

interface PreviewData {
  source: string
  folder: string
  file: string
  note: string
}

const data = ref<PreviewData | null>(null)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | null = null

async function fetchPreview() {
  try {
    const resp = await fetch('/api/config/render-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: props.config }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    data.value = await resp.json()
    error.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    data.value = null
  }
}

watch(
  () => props.config,
  () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(fetchPreview, 400)
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div v-loading="!data && !error" class="update-preview">
    <template v-if="data">
      <div class="pv-row">
        <span class="pv-key">原位置</span>
        <span class="pv-val">{{ data.source }}</span>
      </div>
      <div class="pv-row">
        <span class="pv-key">更新后</span>
        <span class="pv-val">
          {{ data.folder }}/<span class="pv-file">{{ data.file.split('/').pop() }}</span>
        </span>
      </div>
      <div v-if="data.note" class="pv-note">{{ data.note }}</div>
      <div class="pv-sample">示例：有中字、无 4K；番号 SNOS-323，演员 三田真铃</div>
    </template>
    <div v-else-if="error" class="pv-note">预览失败：{{ error }}</div>
  </div>
</template>

<style scoped>
.update-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  min-height: 58px;
}
.pv-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  align-items: baseline;
}
.pv-key {
  flex: none;
  width: 44px;
  color: #909399;
  font-size: 12px;
}
.pv-val {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
}
.pv-file {
  color: var(--el-color-primary);
  font-weight: 600;
}
.pv-note {
  font-size: 12px;
  color: var(--el-color-warning);
}
.pv-sample {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
