<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import FormNode from '../components/FormNode.vue'
import tabsDef from '../settings-tabs.json'

const schema = ref<Record<string, any> | null>(null)
const config = ref<Record<string, any>>({})
const configPath = ref('')
const files = ref<string[]>([])
const currentFile = ref('')
const activeTab = ref(tabsDef[0]?.tab ?? '')
const saving = ref(false)

const defs = computed(() => schema.value?.$defs ?? {})

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
            <div v-for="field in group.fields" :key="field" class="field">
              <div class="field-label" :title="field">{{ fieldTitle(field) }}</div>
              <div class="field-control">
                <FormNode :node="fieldNode(field)" :defs="defs" :model-value="config[field]" @update:model-value="config[field] = $event" />
              </div>
            </div>
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
</style>
