<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

/**
 * 服务器媒体文件选择器：只在「配置的目录白名单」内浏览（不可越界），
 * 列出配置的媒体/字幕扩展名文件。单选选完即回填；多选累计后由确认按钮回填。
 */
const props = defineProps<{
  modelValue: string | string[]
  multiple?: boolean
  placeholder?: string
  /** 覆盖默认媒体/字幕扩展名过滤（逗号分隔，如 ".nfo"） */
  exts?: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: string | string[]): void }>()

const dialog = ref(false)
const current = ref('')
const parent = ref('')
const dirs = ref<string[]>([])
const files = ref<string[]>([])
const roots = ref<string[]>([])
const picked = ref<string[]>([])
const loading = ref(false)

function join(base: string, name: string): string {
  return base.endsWith('/') ? base + name : base + '/' + name
}

async function enter(path: string, silent = false) {
  loading.value = true
  try {
    const extsQ = props.exts ? `&exts=${encodeURIComponent(props.exts)}` : ''
    const d = await fetch(`/api/fs/media-browse?path=${encodeURIComponent(path)}${extsQ}`)
    if (!d.ok) {
      const err = await d.json().catch(() => ({ detail: d.statusText }))
      throw new Error(err.detail ?? d.statusText)
    }
    const data = await d.json()
    if (data.roots && !data.current) {
      // 空路径响应：只有根目录列表，自动进入第一个可用根
      roots.value = data.roots
      if (data.roots.length) return enter(data.roots[0], silent)
      return
    }
    current.value = data.current
    parent.value = data.parent ?? ''
    dirs.value = data.dirs ?? []
    files.value = data.files ?? []
  } catch (e) {
    if (silent) {
      const fallback = roots.value[0] || '/'
      if (path !== fallback) return enter(fallback, true)
      return
    }
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

function open() {
  dialog.value = true
  picked.value = []
  const initial = Array.isArray(props.modelValue) ? props.modelValue[0] : String(props.modelValue ?? '')
  void enter(initial || roots.value[0] || '', true)
}

function pickFile(name: string) {
  const chosen = join(current.value, name)
  if (props.multiple) {
    if (!picked.value.includes(chosen)) picked.value.push(chosen)
    return
  }
  emit('update:modelValue', chosen)
  dialog.value = false
}

function confirmPicked() {
  if (!picked.value.length) {
    ElMessage.warning('请先选择文件')
    return
  }
  emit('update:modelValue', [...picked.value])
  dialog.value = false
}

function onManualInput(value: string | string[]) {
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="file-picker">
    <el-input
      :model-value="Array.isArray(modelValue) ? modelValue.join(' ') : String(modelValue ?? '')"
      :placeholder="placeholder"
      class="picker-input"
      @update:model-value="onManualInput"
    />
    <el-button class="picker-btn" @click="open">📄 选择</el-button>

    <el-dialog v-model="dialog" title="选择媒体文件（仅限配置的目录）" width="680px" top="6vh">
      <div class="roots">
        <el-button v-for="r in roots" :key="r" size="small" @click="enter(r)">📂 {{ r }}</el-button>
      </div>
      <div class="path-bar">
        <el-button size="small" :disabled="!parent" @click="enter(parent)">⬆️ 上级</el-button>
        <span class="cur">{{ current }}</span>
      </div>
      <div v-loading="loading" class="listing">
        <div v-for="d in dirs" :key="d" class="entry" @click="enter(join(current, d))">📁 {{ d }}</div>
        <div v-for="f in files" :key="f" class="entry" :class="{ picked: picked.includes(join(current, f)) }" @click="pickFile(f)">
          🎬 {{ f }}
        </div>
        <div v-if="!dirs.length && !files.length" class="empty">（目录为空）</div>
      </div>
      <div v-if="multiple" class="picked-count">已选 {{ picked.length }} 个文件</div>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button v-if="multiple" type="primary" @click="confirmPicked">确认已选（{{ picked.length }}）</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.file-picker {
  display: flex;
  gap: 8px;
  width: 100%;
}
.picker-input {
  flex: 1;
}
.picker-btn {
  flex-shrink: 0;
}
.roots {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.path-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.cur {
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}
.listing {
  height: 45vh;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px;
}
.entry {
  padding: 7px 10px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}
.entry:hover {
  background: var(--el-color-primary-light-9);
}
.entry.picked {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}
.empty {
  color: #909399;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}
.picked-count {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
