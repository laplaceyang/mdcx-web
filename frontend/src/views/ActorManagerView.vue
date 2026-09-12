<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type EmbyActor } from '../api/client'

const connected = ref(false)
const connecting = ref(false)
const folders = ref<string[]>([])
const actors = ref<EmbyActor[]>([])
const filterActorOnly = ref(true)
const filterMissingImage = ref(false)
const filterMissingOverview = ref(false)
const loading = ref(false)
const keyword = ref('')
const cachedAt = ref('')

const detail = ref<Record<string, any> | null>(null)
const detailDialog = ref(false)
const newOverview = ref('')
const uploadingAvatar = ref(false)

async function restoreCache(): Promise<boolean> {
  try {
    const d = await api.actorsCache()
    if (!d.cached || !d.actors.length) return false
    actors.value = d.actors
    cachedAt.value = d.ts ? new Date(d.ts * 1000).toLocaleString() : ''
    return true
  } catch {
    return false
  }
}

onMounted(async () => {
  // 进页面优先用服务端缓存（actor_cache.db），只有点「刷新列表」才请求 Emby
  if (await restoreCache()) {
    connected.value = true // 有缓存说明之前连成功过
  }
})

async function testConnection() {
  connecting.value = true
  try {
    const r = await api.embyTest()
    connected.value = r.ok
    folders.value = (r.folders as { name?: string }[]).map((f) => String(f.name ?? f))
    ElMessage.success('Emby 连接成功')
  } catch (e) {
    connected.value = false
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    connecting.value = false
  }
}

async function loadActors() {
  loading.value = true
  try {
    const r = await api.embyActors(filterActorOnly.value)
    actors.value = r.actors
    connected.value = true // 刷新列表同样经过 Emby，成功即视为连接正常
    const saved = await api.saveActorsCache(r.actors)
    cachedAt.value = saved.ts ? new Date(saved.ts * 1000).toLocaleString() : ''
    ElMessage.success(`已加载 ${r.actors.length} 个演员`)
  } catch (e) {
    connected.value = false
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  let list = actors.value
  const kw = keyword.value.trim().toLowerCase()
  if (kw) list = list.filter((a) => a.name.toLowerCase().includes(kw))
  if (filterMissingImage.value) list = list.filter((a) => !a.has_image)
  if (filterMissingOverview.value) list = list.filter((a) => !a.has_overview)
  return list
})

async function openDetail(row: EmbyActor) {
  try {
    detail.value = await api.embyActorDetail(row.name)
    newOverview.value = String(detail.value.overview ?? '')
    detailDialog.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function saveDetail() {
  if (!detail.value) return
  try {
    await api.embyActorUpdate(
      {
        name: detail.value.name,
        actor_id: detail.value.id ?? detail.value.actor_id ?? '',
        server_id: detail.value.server_id ?? '',
        existing_overview: String(detail.value.overview ?? ''),
        new_overview: newOverview.value,
      },
      '',
    )
    ElMessage.success('更新请求已提交（结果见日志页）')
    detailDialog.value = false
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onAvatarPick(uploadFile: { raw?: File }) {
  const raw = uploadFile.raw
  if (!raw || !detail.value) return
  uploadingAvatar.value = true
  try {
    const d = await api.embyActorUploadAvatarFile(
      String(detail.value.name),
      String(detail.value.id ?? detail.value.actor_id ?? ''),
      String(detail.value.server_id ?? ''),
      raw,
    )
    if (d.ok) {
      ElMessage.success(d.message)
    } else {
      ElMessage.error(d.message)
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    uploadingAvatar.value = false
  }
}
</script>

<template>
  <div class="emby-view">
    <el-card shadow="never" class="toolbar">
      <el-tag :type="connected ? 'success' : 'danger'" size="small">{{ connected ? '已连接' : '未连接' }}</el-tag>
      <span v-if="folders.length" class="folders">媒体库：{{ folders.join('、') }}</span>
      <el-button :loading="connecting" @click="testConnection">测试连接</el-button>
      <el-divider direction="vertical" />
      <el-checkbox v-model="filterActorOnly" label="仅演员身份" @change="loadActors" />
      <el-checkbox v-model="filterMissingImage" label="头像缺失" />
      <el-checkbox v-model="filterMissingOverview" label="简介缺失" />
      <el-input v-model="keyword" placeholder="搜索演员" style="width: 180px" clearable />
      <el-button :loading="loading" @click="loadActors">刷新列表</el-button>
      <span v-if="cachedAt" class="hint">缓存于 {{ cachedAt }}（共 {{ actors.length }} 条）</span>
      <span class="hint">连接参数在「软件设置 → 演员」页配置（Emby 地址 / API Key / 用户 ID）</span>
    </el-card>

    <el-card shadow="never">
      <el-table :data="filtered" size="small" height="calc(100vh - 280px)">
        <el-table-column prop="name" label="演员" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="openDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="头像" width="80">
          <template #default="{ row }">
            <el-tag :type="row.has_image ? 'success' : 'danger'" size="small">{{ row.has_image ? '有' : '缺' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="简介" width="80">
          <template #default="{ row }">
            <el-tag :type="row.has_overview ? 'success' : 'danger'" size="small">{{ row.has_overview ? '有' : '缺' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="movie_count" label="关联影片" width="90" />
      </el-table>
    </el-card>

    <el-dialog v-model="detailDialog" :title="detail?.name ?? '演员详情'" width="640px">
      <pre v-if="detail" class="detail-pre">{{ JSON.stringify(detail, null, 2) }}</pre>
      <el-input v-model="newOverview" type="textarea" :rows="5" placeholder="新简介（留空表示不修改）" class="mt" />
      <div class="avatar-row mt">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept="image/jpeg,image/png,image/webp"
          :on-change="onAvatarPick"
        >
          <el-button type="primary" plain :loading="uploadingAvatar">📤 上传头像（选择图片后立即上传到 Emby）</el-button>
        </el-upload>
      </div>
      <template #footer>
        <el-button @click="detailDialog = false">取消</el-button>
        <el-button type="primary" @click="saveDetail">提交更新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.emby-view {
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
  flex-wrap: wrap;
  padding: 10px 16px;
}
.folders {
  color: #606266;
  font-size: 13px;
}
.hint {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.detail-pre {
  max-height: 40vh;
  overflow: auto;
  background: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
}
.mt {
  margin-top: 10px;
}
.avatar-row {
  display: flex;
  align-items: center;
}
</style>
