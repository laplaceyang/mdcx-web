<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, mediaUrl, type NfoSummary } from '../api/client'

const roots = ref<string[]>([])
const currentDir = ref('')
const dirs = ref<string[]>([])
const items = ref<NfoSummary[]>([])
const keyword = ref('')
const selected = ref<NfoSummary[]>([])

const editDialog = ref(false)
const editPath = ref('')
const editFields = ref<Record<string, any>>({})
const editImages = ref<Record<string, string>>({})
const nfoDialog = ref(false)
const nfoText = ref('')

const SCALAR_FIELDS: [string, string][] = [
  ['title', '标题'],
  ['originaltitle', '原始标题'],
  ['number', '番号'],
  ['director', '导演'],
  ['release', '发行日期'],
  ['runtime', '片长(分钟)'],
  ['score', '评分'],
  ['year', '年份'],
  ['series', '系列'],
  ['studio', '制作商'],
  ['publisher', '发行商'],
  ['tagline', '标语'],
]
const TEXT_FIELDS: [string, string][] = [
  ['outline', '简介'],
  ['plot', '剧情'],
]

async function browse(path = currentDir.value) {
  try {
    const d = await api.nfoBrowse(path, keyword.value)
    dirs.value = d.dirs
    items.value = d.items
    if (d.current) currentDir.value = d.current
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

function goUp() {
  const parent = currentDir.value.replace(/\/[^/]+\/?$/, '')
  browse(parent || '')
}

async function openItem(row: NfoSummary) {
  try {
    const d = await api.nfoItem(row.path)
    editPath.value = row.path
    editFields.value = d.fields
    editImages.value = d.images
    editDialog.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function saveItem() {
  try {
    await api.nfoSave(editPath.value, editFields.value)
    ElMessage.success('已保存')
    editDialog.value = false
    await browse()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function viewNfo(row: NfoSummary) {
  try {
    const resp = await fetch(`/api/media/file?path=${encodeURIComponent(row.path)}`)
    nfoText.value = await resp.text()
    nfoDialog.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function deleteSelected() {
  const rows = selected.value.length ? selected.value : []
  if (!rows.length) {
    ElMessage.warning('请先勾选要删除的 NFO')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除 ${rows.length} 个 NFO 文件？`, '删除', { type: 'error' })
  } catch {
    return
  }
  for (const row of rows) await api.nfoDelete(row.path)
  ElMessage.success(`已删除 ${rows.length} 个`)
  await browse()
}

async function rescrapeRow(row: NfoSummary) {
  try {
    await api.nfoRescrape(row.path)
    ElMessage.success('已加入重刮')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

// 批量操作
const batchDialog = ref(false)
const batchAction = ref('replace_actor')
const batchValue = ref('')

function openBatch() {
  if (!selected.value.length) {
    ElMessage.warning('请先勾选要批量操作的 NFO')
    return
  }
  batchDialog.value = true
}

async function doBatch() {
  try {
    const r = await api.nfoBatch(
      selected.value.map((s) => s.path),
      batchAction.value,
      batchValue.value,
    )
    ElMessage.success(`批量完成: 成功 ${r.success} / 失败 ${r.failed.length}`)
    batchDialog.value = false
    await browse()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(async () => {
  roots.value = (await api.nfoRoots()).roots
  await browse(roots.value[0] ?? '')
})
</script>

<template>
  <div class="nfo-view">
    <el-card shadow="never" class="toolbar">
      <el-button @click="goUp" :disabled="!currentDir">上级目录</el-button>
      <el-input v-model="keyword" placeholder="关键字过滤" style="width: 220px" clearable @keyup.enter="browse()" />
      <el-button @click="browse()">过滤</el-button>
      <el-button type="danger" plain @click="deleteSelected">删除选中 NFO</el-button>
      <el-button type="primary" plain @click="openBatch">批量操作…</el-button>
      <span class="path">{{ currentDir }}</span>
    </el-card>

    <el-card shadow="never">
      <div class="dirs">
        <el-tag v-for="d in dirs" :key="d" class="dir-tag" @click="browse(d)">{{ d.split('/').pop() || d }}</el-tag>
      </div>
      <el-table
        :data="items"
        size="small"
        height="calc(100vh - 330px)"
        @selection-change="(rows: any[]) => (selected = rows)"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column label="封面" width="64">
          <template #default="{ row }">
            <el-image
              v-if="row.has_poster"
              :src="mediaUrl(row.dir + '/poster.jpg') ?? ''"
              fit="cover"
              style="width: 42px; height: 58px"
              :preview-src-list="[mediaUrl(row.dir + '/poster.jpg') ?? '']"
              preview-teleported
            />
            <span v-else class="noimg">无</span>
          </template>
        </el-table-column>
        <el-table-column prop="number" label="番号" width="150" />
        <el-table-column prop="title" label="标题" min-width="260" show-overflow-tooltip />
        <el-table-column label="演员" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.actor.join(', ') }}</template>
        </el-table-column>
        <el-table-column prop="series" label="系列" width="120" show-overflow-tooltip />
        <el-table-column prop="release" label="发行" width="100" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openItem(row)">编辑</el-button>
            <el-button size="small" text @click="viewNfo(row)">查看</el-button>
            <el-button size="small" text type="warning" @click="rescrapeRow(row)">重刮</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editDialog" title="编辑 NFO" width="760px" top="5vh">
      <div class="edit-body">
        <div class="edit-form">
          <div v-for="[name, label] in SCALAR_FIELDS" :key="name" class="field">
            <span class="label">{{ label }}</span>
            <el-input v-model="editFields[name]" size="small" />
          </div>
          <div v-for="[name, label] in TEXT_FIELDS" :key="name" class="field">
            <span class="label">{{ label }}</span>
            <el-input v-model="editFields[name]" type="textarea" :rows="3" size="small" />
          </div>
          <div class="field">
            <span class="label">演员（逗号分隔）</span>
            <el-input size="small" :model-value="(editFields.actor as string[])?.join(', ')"
              @update:model-value="editFields.actor = $event.split(',').map((s: string) => s.trim()).filter(Boolean)" />
          </div>
          <div class="field">
            <span class="label">标签（逗号分隔）</span>
            <el-input size="small" :model-value="(editFields.tag as string[])?.join(', ')"
              @update:model-value="editFields.tag = $event.split(',').map((s: string) => s.trim()).filter(Boolean)" />
          </div>
        </div>
        <div class="edit-images">
          <el-image v-for="(src, key) in editImages" :key="key" :src="mediaUrl(src) ?? ''" fit="cover" class="img"
            :preview-src-list="[mediaUrl(src) ?? '']" preview-teleported />
        </div>
      </div>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="saveItem">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchDialog" title="批量操作" width="480px">
      <el-select v-model="batchAction" class="mb">
        <el-option label="替换演员（覆盖）" value="replace_actor" />
        <el-option label="添加标签" value="add_tag" />
        <el-option label="删除标签" value="del_tag" />
        <el-option label="统一系列名" value="set_series" />
      </el-select>
      <el-input v-model="batchValue" placeholder="值（演员/标签逗号分隔，系列名直接填）" />
      <p class="hint">将对选中的 {{ selected.length }} 个 NFO 生效</p>
      <template #footer>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button type="primary" @click="doBatch">执行</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="nfoDialog" title="NFO 内容" width="720px" top="6vh">
      <pre class="nfo-pre">{{ nfoText }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.nfo-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.toolbar :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
}
.path {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 40%;
}
.dirs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.dir-tag {
  cursor: pointer;
}
.noimg {
  color: #c0c4cc;
  font-size: 12px;
}
.edit-body {
  display: flex;
  gap: 16px;
}
.edit-form {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.field .label {
  font-size: 12px;
  color: #909399;
}
.edit-images {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.edit-images .img {
  width: 140px;
  height: 96px;
  border-radius: 4px;
}
.mb {
  margin-bottom: 10px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
.nfo-pre {
  max-height: 65vh;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
