<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import FormNode from '../components/FormNode.vue'
import FieldPriorityEditor from '../components/FieldPriorityEditor.vue'
import SiteConfigEditor from '../components/SiteConfigEditor.vue'
import UpdatePreview from '../components/UpdatePreview.vue'
import tabsDef from '../settings-tabs.json'

const schema = ref<Record<string, any> | null>(null)
const config = ref<Record<string, any>>({})
const configPath = ref('')
const files = ref<string[]>([])
const currentFile = ref('')
const activeTab = ref(tabsDef[0]?.tab ?? '')
const saving = ref(false)

const defs = computed(() => schema.value?.$defs ?? {})

// settings-tabs.json 的 fields 数组支持混入分区条目：{"section": "...", "desc": "...", "preview": "update"}
type TabEntry = string | { section: string; desc?: string; preview?: string }

type FieldEntry = { kind: 'section'; entry: { section: string; desc?: string; preview?: string } } | { kind: 'field'; name: string }

function toEntries(fields: TabEntry[]): FieldEntry[] {
  return fields.map((f) =>
    typeof f === 'object' && f !== null && 'section' in f
      ? { kind: 'section', entry: f }
      : { kind: 'field', name: String(f) },
  )
}

// 字段联动显隐：更新/读取相关配置只在对应工作模式下出现（settings-tabs.json 分区同理）
function isUpdateReadMode(): boolean {
  const m = Number(config.value.main_mode ?? 1)
  return m === 3 || m === 4
}

const FIELD_VISIBLE: Record<string, () => boolean> = {
  update_mode: isUpdateReadMode,
  update_a_folder: () => isUpdateReadMode() && String(config.value.update_mode ?? '').includes('a'),
  update_b_folder: () => isUpdateReadMode() && String(config.value.update_mode ?? '').includes('b'),
  update_d_folder: () => isUpdateReadMode() && config.value.update_mode === 'd',
  update_c_filetemplate: isUpdateReadMode,
  update_titletemplate: isUpdateReadMode,
  read_mode: () => Number(config.value.main_mode ?? 1) === 4,
}

function fieldVisible(name: string): boolean {
  const rule = FIELD_VISIBLE[name]
  return rule ? rule() : true
}

const updateHints = computed<string[]>(() => {
  const hints: string[] = []
  if (!isUpdateReadMode()) return hints
  hints.push('此模式下文件名走「更新·文件名模板（C）」，不走「命名格式」页签的文件模板——想要 -C 后缀记得两边保持一致')
  if (Number(config.value.main_mode ?? 1) === 3 && config.value.update_mode === 'c' && !config.value.success_file_rename) {
    hints.push('原地刷新 + 未开「成功后重命名文件」：文件与字幕完全不动，仅重写 NFO/图片')
  }
  return hints
})

function fieldNode(name: string): Record<string, any> {
  return schema.value?.properties?.[name] ?? { type: 'string' }
}

function fieldTitle(name: string): string {
  const node = fieldNode(name)
  const title = node.title ?? node.$ref
  if (title && title !== name) return String(title)
  const resolved = node.$ref ? defs.value[String(node.$ref).split('/').pop() ?? ''] : null
  return String(resolved?.title ?? name)
}

function isNested(name: string): boolean {
  const node = fieldNode(name)
  const ref = String(node.$ref ?? '')
  return ref.includes('$defs')
}

function loadLocal() {
  const saved = localStorage.getItem('mdcx.settings.tab')
  if (saved && tabsDef.some((t) => t.tab === saved)) activeTab.value = saved
}

onMounted(async () => {
  loadLocal()
  await reload()
})

async function reload() {
  try {
    const [cfg, sch, fs] = await Promise.all([api.config(), fetch('/api/config/schema').then((r) => r.json()), api.configFiles()])
    config.value = cfg.config
    configPath.value = cfg.path
    schema.value = sch
    files.value = fs.files
    currentFile.value = fs.current
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function save() {
  saving.value = true
  try {
    const resp = await api.putConfig(config.value)
    if (resp.errors?.length) {
      ElMessage.warning(`已保存，但有提示：${resp.errors.join('；')}`)
    } else {
      ElMessage.success('设置已保存')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    saving.value = false
  }
}

async function onSwitchFile(name: string) {
  if (name === currentFile.value) return
  try {
    await ElMessageBox.confirm(`切换到配置文件「${name}」？未保存的修改将丢失。`, '切换配置', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.switchConfig(name)
    await reload()
    ElMessage.success(`已切换到 ${name}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onReset() {
  try {
    await ElMessageBox.confirm('确定恢复默认设置？当前配置将被覆盖！', '初始化配置', { type: 'error' })
  } catch {
    return
  }
  try {
    await api.resetConfig()
    await reload()
    ElMessage.success('已恢复默认设置')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

function onTabChange(name: string) {
  localStorage.setItem('mdcx.settings.tab', name)
}
</script>

<template>
  <div class="settings-view">
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-row">
        <el-select :model-value="currentFile" class="file-select" @change="onSwitchFile">
          <el-option v-for="f in files" :key="f" :label="f" :value="f" />
        </el-select>
        <span class="path" :title="configPath">{{ configPath }}</span>
        <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
        <el-button type="danger" plain @click="onReset">初始化配置</el-button>
      </div>
    </el-card>

    <el-card v-if="schema" shadow="never" class="form-card">
      <el-tabs v-model="activeTab" tab-position="left" class="tabs" @tab-change="onTabChange">
        <el-tab-pane v-for="group in tabsDef" :key="group.tab" :name="group.tab" :label="group.tab">
          <div class="fields">
            <template v-for="(entry, idx) in toEntries(group.fields as TabEntry[])" :key="idx">
              <!-- 分区标题：更新/读取整块只在对应工作模式下显示 -->
              <div v-if="entry.kind === 'section' && isUpdateReadMode()" class="section-head">
                <div class="section-title">{{ entry.entry.section }}</div>
                <div v-if="entry.entry.desc" class="section-desc">{{ entry.entry.desc }}</div>
                <el-alert
                  v-for="(h, hi) in updateHints"
                  :key="hi"
                  :title="h"
                  type="info"
                  :closable="false"
                  class="section-hint"
                />
                <UpdatePreview v-if="entry.entry.preview === 'update'" :config="config" class="section-preview" />
              </div>
              <div v-else-if="entry.kind === 'field' && fieldVisible(entry.name)" class="field">
                <div class="field-label" :title="entry.name">{{ fieldTitle(entry.name) }}</div>
                <div class="field-control wide">
                  <!-- 三个复杂结构使用专用编辑器（桌面版专用对话框的 web 版） -->
                  <FieldPriorityEditor
                    v-if="entry.name === 'field_configs'"
                    variant="field"
                    :model-value="config[entry.name]"
                    @update:model-value="config[entry.name] = $event"
                  />
                  <FieldPriorityEditor
                    v-else-if="entry.name === 'type_field_configs'"
                    variant="priority"
                    :model-value="config[entry.name]"
                    @update:model-value="config[entry.name] = $event"
                  />
                  <SiteConfigEditor
                    v-else-if="entry.name === 'site_configs'"
                    :model-value="config[entry.name]"
                    @update:model-value="config[entry.name] = $event"
                  />
                  <FormNode
                    v-else
                    :node="fieldNode(entry.name)"
                    :defs="defs"
                    :field-name="entry.name"
                    :model-value="config[entry.name]"
                    @update:model-value="config[entry.name] = $event"
                  />
                </div>
              </div>
            </template>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.settings-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.toolbar :deep(.el-card__body) {
  padding: 10px 16px;
}
.toolbar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.file-select {
  width: 200px;
}
.path {
  flex: 1;
  color: #909399;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.form-card {
  flex: 1;
}
.tabs {
  min-height: calc(100vh - 220px);
}
.tabs :deep(.el-tabs__content) {
  height: calc(100vh - 220px);
  overflow: auto;
  padding-right: 8px;
}
.fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 760px;
}
.field {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 12px;
  align-items: start;
}
.field-label {
  font-size: 13px;
  color: #303133;
  padding-top: 5px;
  word-break: break-all;
}
.section-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.section-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
.section-hint {
  margin-top: 2px;
}
.section-preview {
  margin-top: 4px;
}
</style>

.field-control.wide {
  max-width: none;
}
