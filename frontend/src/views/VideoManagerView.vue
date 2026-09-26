<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type EmbyLibrary, type EmbyVideo } from '../api/client'

const connected = ref(false)
const loading = ref(false)
const refreshing = ref(false)
const libraries = ref<EmbyLibrary[]>([])
const libraryId = ref('')
const defaultLibraryId = ref('')
const videos = ref<EmbyVideo[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 200
const keyword = ref('')
const appliedKeyword = ref('')
const cachedAt = ref('')
const deletingId = ref('')
const dupOnly = ref(false)

const isDefaultLib = computed(() => !!defaultLibraryId.value && libraryId.value === defaultLibraryId.value)

const TYPE_LABELS: Record<string, string> = {
  Movie: '电影',
  Series: '电视剧',
  Episode: '剧集',
  Video: '视频',
  MusicVideo: 'MV',
}
function typeLabel(t: string): string {
  return TYPE_LABELS[t] ?? t
}

function fmtSize(n: number): string {
  if (!n) return '-'
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + ' GB'
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + ' MB'
  return (n / 1024).toFixed(0) + ' KB'
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function loadVideos() {
  if (!libraryId.value) return
  loading.value = true
  try {
    const libType = libraries.value.find((l) => l.id === libraryId.value)?.type ?? ''
    const r = await api.embyVideos(libraryId.value, (page.value - 1) * pageSize, pageSize, appliedKeyword.value, libType, dupOnly.value)
    videos.value = r.videos
    total.value = r.total
    cachedAt.value = r.ts ? new Date(r.ts * 1000).toLocaleString() : ''
    connected.value = true
  } catch (e) {
    connected.value = false
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

async function refreshList() {
  if (!libraryId.value) return
  if (!isDefaultLib.value) {
    ElMessage.warning('番号提取与缓存仅对「软件设置 → 服务器」配置的视频库生效')
    return
  }
  refreshing.value = true
  try {
    const libType = libraries.value.find((l) => l.id === libraryId.value)?.type ?? ''
    await api.embyRefreshVideos(libraryId.value, libType)
    ElMessage.success('已从 Emby 重新拉取并更新番号缓存')
    page.value = 1
    await loadVideos()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    refreshing.value = false
  }
}

async function deleteVideo(row: EmbyVideo) {
  if (!isDefaultLib.value || !libraryId.value || deletingId.value) return
  const target = row.type === 'Series' ? `剧集《${row.name}》及其全部集` : `「${row.name}」`
  try {
    await ElMessageBox.confirm(
      `将从 Emby 删除${target}，并同步移出本地列表缓存；源文件是否一并删除取决于 Emby 服务器设置。确认删除？`,
      '删除视频',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  deletingId.value = row.id
  try {
    await api.embyDeleteVideo(libraryId.value, row.id)
    ElMessage.success(`已删除「${row.name}」`)
    // 删除的是本页最后一条时回退一页，避免停在空页
    if (videos.value.length <= 1 && page.value > 1) page.value -= 1
    await loadVideos()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    deletingId.value = ''
  }
}

async function loadLibraries() {
  loading.value = true
  try {
    const [r, cfg] = await Promise.all([api.embyLibraries(), api.config()])
    libraries.value = r.libraries
    connected.value = true
    // 视频库以「软件设置 → 服务器 → 视频库」为准；番号提取、缓存与删除也只对它生效
    defaultLibraryId.value = String(cfg.config.video_library_id ?? '').trim()
    libraryId.value =
      defaultLibraryId.value && libraries.value.some((l) => l.id === defaultLibraryId.value)
        ? defaultLibraryId.value
        : (libraries.value[0]?.id ?? '')
    page.value = 1
    if (libraryId.value) {
      await loadVideos()
    } else {
      ElMessage.warning('Emby 里没有可用媒体库')
    }
  } catch (e) {
    connected.value = false
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function onLibraryChange() {
  // v-model 已更新 libraryId；页面内切换仅本次会话有效，默认库始终以设置页为准
  page.value = 1
  cachedAt.value = ''
  dupOnly.value = false
  loadVideos()
}

function toggleDupOnly() {
  dupOnly.value = !dupOnly.value
  page.value = 1
  loadVideos()
}

function onSearch() {
  appliedKeyword.value = keyword.value.trim()
  page.value = 1
  loadVideos()
}

function onPageChange(p: number) {
  page.value = p
  loadVideos()
}

onMounted(loadLibraries)
</script>

<template>
  <div class="video-view">
    <el-card shadow="never" class="toolbar">
      <el-tag :type="connected ? 'success' : 'danger'" size="small">{{ connected ? '已连接' : '未连接' }}</el-tag>
      <span class="label">视频库</span>
      <el-select
        v-model="libraryId"
        placeholder="选择视频库"
        style="width: 220px"
        :loading="loading"
        @change="onLibraryChange"
      >
        <el-option v-for="l in libraries" :key="l.id" :label="l.name" :value="l.id" />
      </el-select>
      <el-input
        v-model="keyword"
        placeholder="搜索标题/番号/路径"
        style="width: 200px"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button @click="onSearch">搜索</el-button>
      <el-button :loading="refreshing" @click="refreshList">刷新列表</el-button>
      <el-button :loading="loading" @click="loadLibraries">重连</el-button>
      <el-button v-if="isDefaultLib" :type="dupOnly ? 'warning' : ''" :disabled="loading" @click="toggleDupOnly">
        重复番号
      </el-button>
      <span class="hint">
        共 {{ total }} 条
        <template v-if="isDefaultLib">
          · <template v-if="cachedAt">缓存于 {{ cachedAt }}，</template>点「刷新列表」重新拉取番号
        </template>
        <template v-else>· 番号提取与删除仅对「软件设置 → 服务器」配置的视频库生效</template>
        · 连接参数在同页「服务器」页签配置
      </span>
    </el-card>

    <el-card shadow="never">
      <el-table :data="videos" size="small" height="calc(100vh - 320px)" v-loading="loading">
        <el-table-column label="封面" width="70">
          <template #default="{ row }">
            <el-image
              v-if="row.thumb"
              :src="row.thumb"
              :preview-src-list="row.image ? [row.image] : []"
              preview-teleported
              hide-on-click-modal
              class="thumb"
              fit="cover"
              lazy
            />
            <span v-else class="no-img">无图</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isDefaultLib" prop="number" label="番号" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.number">{{ row.number }}</span>
            <span v-else class="no-img">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="year" label="年份" width="70" />
        <el-table-column label="大小" width="90">
          <template #default="{ row }">{{ fmtSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="path" label="路径" min-width="280" show-overflow-tooltip />
        <el-table-column prop="date_created" label="入库日期" width="100" />
        <el-table-column v-if="isDefaultLib" label="操作" width="76" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :loading="deletingId === row.id" @click="deleteVideo(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          layout="total, prev, pager, next, jumper"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="onPageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.video-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
}
.label {
  font-size: 13px;
  color: #606266;
}
.hint {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.thumb {
  width: 44px;
  height: 60px;
  border-radius: 4px;
  display: block;
  cursor: zoom-in;
}
.no-img {
  color: #c0c4cc;
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}
</style>
