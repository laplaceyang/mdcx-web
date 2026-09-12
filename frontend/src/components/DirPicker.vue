<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

/**
 * 服务器目录/文件选择器：输入框 + 📁 弹窗浏览。
 * - 值为字符串时选择单个路径；multiple 时值为 string[]（逐次追加）
 * - append-sep：非空时选择结果以该分隔符追加（如媒体路径的 "|"）
 * - files：弹窗内同时列出文件并允许选中文件
 * 输入框保留可编辑，兼容相对路径/容器路径等手写场景。
 */
const props = defineProps<{
  modelValue: string | string[]
  multiple?: boolean
  files?: boolean
  appendSep?: string
  placeholder?: string
  /** 选择的是目录时自动补上该文件名（用于期望文件路径的字段，如 info_database.db） */
  dirFileAppend?: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: string | string[]): void }>()

const dialog = ref(false)
const current = ref('')
const parent = ref('')
const dirs = ref<string[]>([])
const files = ref<string[]>([])
const loading = ref(false)
const appendMode = ref(false)
const LAST_DIR_KEY = 'mdcx.dirpicker.last'
const shortcuts = ref<{ home: string; data_folder: string; media: string[] }>({
  home: '',
  data_folder: '',
  media: [],
})

// 当前值的分段（多路径 | 分隔 / multiple 数组），弹窗内可逐个删除
const segments = computed(() => {
  if (props.multiple) return Array.isArray(props.modelValue) ? [...props.modelValue] : []
  const sep = props.appendSep ?? '|'
  return String(props.modelValue ?? '')
    .split(sep)
    .map((s) => s.trim())
    .filter(Boolean)
})

function setSegments(list: string[]) {
  if (props.multiple) {
    emit('update:modelValue', list)
  } else {
    emit('update:modelValue', list.join(props.appendSep ?? '|'))
  }
}

function removeSegment(index: number) {
  const list = segments.value.filter((_, i) => i !== index)
  setSegments(list)
}

function join(base: string, name: string): string {
  return base.endsWith('/') ? base + name : base + '/' + name
}

async function enter(path: string, silent = false) {
  loading.value = true
  try {
    const d = await fetch(`/api/fs/browse?path=${encodeURIComponent(path)}&with_files=${props.files ? 1 : 0}`)
    if (!d.ok) {
      const err = await d.json().catch(() => ({ detail: d.statusText }))
      throw new Error(err.detail ?? d.statusText)
    }
    const data = await d.json()
    current.value = data.current
    parent.value = data.parent
    dirs.value = data.dirs
    files.value = data.files ?? []
    try {
      localStorage.setItem(LAST_DIR_KEY, data.current) // 记住浏览位置，下次打开默认到这里
    } catch {
      /* ignore */
    }
  } catch (e) {
    if (silent) {
      // 初始定位失败（配置里是不存在的路径等）→ 回退主目录/根目录
      const fallback = shortcuts.value.home || '/'
      if (path !== fallback) return enter(fallback, true)
      return
    }
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function open() {
  dialog.value = true
  appendMode.value = false
  if (!shortcuts.value.home) {
    try {
      shortcuts.value = await fetch('/api/fs/shortcuts').then((r) => r.json())
    } catch {
      /* ignore */
    }
  }
  let last = ''
  try {
    last = localStorage.getItem(LAST_DIR_KEY) ?? ''
  } catch {
    /* ignore */
  }
  const firstSegment = Array.isArray(props.modelValue) ? props.modelValue[0] : String(props.modelValue ?? '').split(props.appendSep ?? '|')[0]
  await enter(last || firstSegment || shortcuts.value.home || '/', true)
}

// 选择行为：默认替换整个值；勾选"追加"时才拼接到现有值后面
function applyChosen(chosen: string) {
  if (props.multiple) {
    const list = appendMode.value ? [...segments.value] : []
    if (!list.includes(chosen)) list.push(chosen)
    emit('update:modelValue', list)
  } else if (appendMode.value && props.modelValue) {
    const parts = segments.value
    if (!parts.includes(chosen)) parts.push(chosen)
    emit('update:modelValue', parts.join(props.appendSep ?? '|'))
  } else {
    emit('update:modelValue', chosen)
  }
}

function pick(name: string) {
  applyChosen(join(current.value, name))
  if (!props.multiple) dialog.value = false
}

function pickCurrent() {
  let chosen = current.value
  if (props.dirFileAppend && !chosen.endsWith(props.dirFileAppend)) {
    chosen = join(chosen, props.dirFileAppend) // 目录 → 自动补默认文件名
  }
  applyChosen(chosen)
  if (!props.multiple) dialog.value = false
}

function onManualInput(value: string | string[]) {
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="dir-picker">
    <el-input
      :model-value="Array.isArray(modelValue) ? modelValue.join(', ') : String(modelValue ?? '')"
      :placeholder="placeholder"
      class="picker-input"
      @update:model-value="onManualInput"
    />
    <el-button class="picker-btn" @click="open">📁 浏览</el-button>

    <el-dialog v-model="dialog" title="选择服务器目录" width="640px" top="6vh">
      <div class="shortcuts">
        <el-button v-if="shortcuts.home" size="small" @click="enter(shortcuts.home)">🏠 主目录</el-button>
        <el-button v-if="shortcuts.data_folder" size="small" @click="enter(shortcuts.data_folder)">🗂️ 配置目录</el-button>
        <el-button v-for="m in shortcuts.media" :key="m" size="small" @click="enter(m)">🎬 {{ m }}</el-button>
        <el-button size="small" @click="enter('/')"> / </el-button>
      </div>
      <div class="path-bar">
        <el-button size="small" :disabled="!parent" @click="enter(parent)">⬆️ 上级</el-button>
        <span class="cur">{{ current }}</span>
      </div>
      <div v-loading="loading" class="listing">
        <div v-for="d in dirs" :key="d" class="entry" @click="enter(join(current, d))">📁 {{ d }}</div>
        <div v-for="f in files" :key="f" class="entry file" @click="pick(f)">📄 {{ f }}</div>
        <div v-if="!dirs.length && !files.length" class="empty">（空目录）</div>
      </div>
      <div v-if="multiple || appendSep" class="picked">
        <span class="picked-label">当前值：</span>
        <el-tag
          v-for="(seg, i) in segments"
          :key="seg"
          size="small"
          closable
          class="picked-tag"
          @close="removeSegment(i)"
        >
          {{ seg }}
        </el-tag>
        <span v-if="!segments.length" class="picked-empty">（空）</span>
        <el-checkbox v-model="appendMode" size="small" class="picked-append">选择后追加（不覆盖）</el-checkbox>
      </div>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="pickCurrent">
          {{ files ? '选择当前目录' : '选择此目录' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.dir-picker {
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
.shortcuts {
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
.entry.file {
  color: #606266;
}
.empty {
  color: #909399;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}
.picked {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.picked-label {
  flex-shrink: 0;
}
.picked-tag {
  max-width: 100%;
}
.picked-empty {
  color: #c0c4cc;
}
.picked-append {
  margin-left: auto;
}
</style>
