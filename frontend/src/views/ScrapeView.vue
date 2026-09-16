<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, mediaUrl, videoUrl, type ResultItem, type ResumeInfo } from '../api/client'
import { useScrapeStore } from '../stores/scrape'
import DirPicker from '../components/DirPicker.vue'

const scrape = useScrapeStore()

// 媒体路径（开始刮削左侧展示，可就地修改并自动保存；手动输入防抖）
const mediaPath = ref('')
const config = ref<Record<string, any> | null>(null)
let saveTimer: number | undefined

async function loadConfig() {
  try {
    config.value = (await api.config()).config
    mediaPath.value = String(config.value?.media_path ?? '')
  } catch {
    /* ignore */
  }
}

function onMediaPathChange(value: string | string[]) {
  mediaPath.value = String(value)
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => void saveMediaPath(), 600)
}

async function saveMediaPath() {
  if (!config.value) return
  config.value.media_path = mediaPath.value
  try {
    await api.putConfig(config.value)
    ElMessage.success('媒体路径已保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(loadConfig)

const activeTab = ref<'succ' | 'fail' | 'progress'>('succ')
const selected = ref<ResultItem | null>(null)
const resumeDialog = ref(false)
const resumeInfo = ref<ResumeInfo | null>(null)
const nfoDialog = ref(false)
const nfoText = ref('')
const nfoPath = ref('')

const filtered = computed(() => scrape.results.filter((r) => r.status === activeTab.value))
const succCount = computed(() => scrape.results.filter((r) => r.status === 'succ').length)
const failCount = computed(() => scrape.results.filter((r) => r.status === 'fail').length)

// ===== 刮削中页签：本次任务实时进度 =====
const donePercent = computed(() => {
  const c = scrape.status.counts
  return c.total > 0 ? Math.round((c.done / c.total) * 100) : 0
})
const elapsedText = computed(() => {
  const s = Math.max(0, Math.round(scrape.status.elapsed))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
})

interface Row { number: string; title: string; actor: string; release: string }

function toRow(item: ResultItem): Row {
  const data = (item.show?.data ?? {}) as Record<string, unknown>
  const actors = Array.isArray(data.actor) ? (data.actor as string[]).join(', ') : String(data.actor ?? '')
  return {
    number: item.real_number || String(data.number ?? ''),
    title: String(data.title ?? ''),
    actor: actors,
    release: String(data.release ?? ''),
  }
}

const tableRows = computed(() => filtered.value.map((r) => ({ item: r, ...toRow(r) })))

const detail = computed(() => {
  if (!selected.value) return null
  const data = (selected.value.show?.data ?? {}) as Record<string, unknown>
  const other = selected.value.show?.other ?? {}
  const tags = Array.isArray(data.tags) ? (data.tags as string[]).join(' / ') : ''
  const actors = Array.isArray(data.actor) ? (data.actor as string[]).join(', ') : String(data.actor ?? '')
  return { data, other, tags, actors }
})

async function onStart() {
  try {
    const info = await api.resumeInfo()
    if (info.available) {
      resumeInfo.value = info
      resumeDialog.value = true
      return
    }
  } catch {
    /* 查询失败则直接开始 */
  }
  await doStart('default')
}

async function doStart(mode: 'default' | 'again') {
  try {
    await api.scrapeStart(mode)
    ElMessage.success('刮削已开始')
    await scrape.refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onResume() {
  resumeDialog.value = false
  try {
    await api.scrapeResume()
    ElMessage.success('已从剩余任务继续刮削')
    await scrape.refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onStop() {
  try {
    await ElMessageBox.confirm('确定要停止刮削吗？', '停止刮削', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.scrapeStop()
    ElMessage.info('停止请求已发送')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onClear() {
  await api.clearResults()
  scrape.resetResults([])
  selected.value = null
}

function onRowContext(event: MouseEvent, item: ResultItem) {
  selected.value = item
  showMenu(event)
}

const menu = ref({ show: false, x: 0, y: 0 })
function showMenu(event: MouseEvent) {
  menu.value = { show: true, x: event.clientX, y: event.clientY }
}
function closeMenu() {
  menu.value.show = false
}

async function onPlay() {
  closeMenu()
  const item = selected.value
  if (!item) return
  const video = videoUrl(item.show?.file_info?.file_path as string)
  if (video) window.open(video, '_blank')
}

async function onOpenNfo() {
  closeMenu()
  const item = selected.value
  if (!item) return
  const filePath = String(item.show?.file_info?.file_path ?? '')
  const nfo = filePath.replace(/\.[^.]+$/, '.nfo')
  try {
    const resp = await fetch(`/api/media/file?path=${encodeURIComponent(nfo)}`)
    if (!resp.ok) {
      ElMessage.warning('未找到对应 NFO 文件')
      return
    }
    nfoText.value = await resp.text()
    nfoPath.value = nfo
    nfoDialog.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onRescrape() {
  closeMenu()
  const item = selected.value
  if (!item) return
  const filePath = String(item.show?.file_info?.file_path ?? '')
  try {
    await api.scrapeStart('again', [filePath])
    ElMessage.success('已加入重刮')
    await scrape.refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

function onSelectRow(item: ResultItem) {
  selected.value = item
}
</script>

<template>
  <div class="scrape-view" @click="closeMenu">
    <el-card class="toolbar" shadow="never">
      <div class="media-path-box" title="媒体路径（刮削的目标目录，可就地修改）">
        <span class="media-label">媒体路径</span>
        <DirPicker
          :model-value="mediaPath"
          append-sep="|"
          placeholder="先在右侧 📁 选择媒体目录"
          @update:model-value="onMediaPathChange"
        />
      </div>
      <el-button type="primary" :disabled="scrape.running || scrape.stopping" @click="onStart">
        开始刮削
      </el-button>
      <el-button type="danger" :disabled="!scrape.running" @click="onStop">停止</el-button>
      <el-button :disabled="scrape.running || scrape.stopping" @click="doStart('again')">按失败列表重刮</el-button>
      <el-button plain @click="onClear">清空结果</el-button>
      <span class="hint">右键结果行：播放 / 查看 NFO / 重刮</span>
    </el-card>

    <div class="content">
      <el-card class="results" shadow="never">
        <el-tabs v-model="activeTab">
          <el-tab-pane name="succ">
            <template #label>成功 ({{ succCount }})</template>
            <el-table
              :data="tableRows"
              height="calc(100vh - 320px)"
              size="small"
              highlight-current-row
              @row-click="({ item }: any) => onSelectRow(item)"
              @row-contextmenu="({ item }: any, _col: any, ev: MouseEvent) => onRowContext(ev, item)"
            >
              <el-table-column prop="number" label="番号" width="160" />
              <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
              <el-table-column prop="actor" label="演员" min-width="150" show-overflow-tooltip />
              <el-table-column prop="release" label="发行日期" width="110" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane name="fail">
            <template #label>失败 ({{ failCount }})</template>
            <el-table
              :data="tableRows"
              height="calc(100vh - 320px)"
              size="small"
              highlight-current-row
              @row-click="({ item }: any) => onSelectRow(item)"
              @row-contextmenu="({ item }: any, _col: any, ev: MouseEvent) => onRowContext(ev, item)"
            >
              <el-table-column prop="number" label="番号" width="160" />
              <el-table-column prop="title" label="文件" min-width="300" show-overflow-tooltip />
              <el-table-column label="操作" width="90">
                <template #default="{ row }">
                  <el-button size="small" text type="primary" @click.stop="selected = row.item; onRescrape()">重刮</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane name="progress">
            <template #label>刮削中 ({{ scrape.status.counts.in_progress }})</template>
            <div class="progress-pane">
              <el-progress
                :percentage="donePercent"
                :stroke-width="16"
                :status="scrape.running ? undefined : donePercent >= 100 ? 'success' : undefined"
              />
              <el-descriptions :column="3" size="small" border class="stat">
                <el-descriptions-item label="任务总数">{{ scrape.status.counts.total }}</el-descriptions-item>
                <el-descriptions-item label="已完成">{{ scrape.status.counts.done }}</el-descriptions-item>
                <el-descriptions-item label="刮削中">{{ scrape.status.counts.in_progress }}</el-descriptions-item>
                <el-descriptions-item label="成功">{{ scrape.status.counts.succ }}</el-descriptions-item>
                <el-descriptions-item label="失败">{{ scrape.status.counts.fail }}</el-descriptions-item>
                <el-descriptions-item label="已用时间">{{ elapsedText }}</el-descriptions-item>
              </el-descriptions>
              <pre class="current-file">{{ scrape.currentFileLabel || (scrape.running ? '（正在分配任务…）' : '（当前没有正在刮削的任务）') }}</pre>
              <div v-if="scrape.scrapeInfo" class="eta">{{ scrape.scrapeInfo }}</div>
              <div class="note">
                统计为「本次任务」口径：每次点「开始刮削」都会清零重新累计；成功/失败按视频文件计数，
                同一影片的多个分部（multi-part）会合并进输出目录的同一个文件夹。历史刮削成果以输出目录为准，本页不保留。
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <el-card v-if="detail" class="detail" shadow="never">
        <div class="detail-head">
          <div class="images">
            <el-image
              :src="mediaUrl(detail.other?.poster_path) ?? undefined"
              :preview-src-list="[mediaUrl(detail.other?.poster_path) ?? '']"
              fit="cover"
              class="poster"
              preview-teleported
            >
              <template #error><div class="img-slot">暂无封面</div></template>
            </el-image>
            <el-image
              :src="mediaUrl(detail.other?.thumb_path) ?? undefined"
              :preview-src-list="[mediaUrl(detail.other?.thumb_path) ?? '']"
              fit="cover"
              class="thumb"
              preview-teleported
            >
              <template #error><div class="img-slot">暂无缩略图</div></template>
            </el-image>
          </div>
          <div class="meta">
            <div class="number">{{ detail.data.number }}</div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="标题" :span="2">{{ detail.data.title }}</el-descriptions-item>
              <el-descriptions-item label="演员" :span="2">{{ detail.actors }}</el-descriptions-item>
              <el-descriptions-item label="导演">{{ detail.data.director || '-' }}</el-descriptions-item>
              <el-descriptions-item label="发行日期">{{ detail.data.release || '-' }}</el-descriptions-item>
              <el-descriptions-item label="片长">{{ detail.data.runtime || '-' }} 分钟</el-descriptions-item>
              <el-descriptions-item label="评分">{{ detail.data.score || '-' }}</el-descriptions-item>
              <el-descriptions-item label="系列">{{ detail.data.series || '-' }}</el-descriptions-item>
              <el-descriptions-item label="制作商">{{ detail.data.studio || '-' }}</el-descriptions-item>
              <el-descriptions-item label="发行商">{{ detail.data.publisher || '-' }}</el-descriptions-item>
              <el-descriptions-item label="标签" :span="2">{{ detail.tags || '-' }}</el-descriptions-item>
              <el-descriptions-item label="简介" :span="2">
                <div class="outline">{{ detail.data.outline || '-' }}</div>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </el-card>
      <el-card v-else class="detail" shadow="never">
        <el-empty description="点击结果查看详情" :image-size="80" />
      </el-card>
    </div>

    <!-- 断点续刮确认（对应桌面版三选弹窗） -->
    <el-dialog v-model="resumeDialog" title="继续刮削" width="560px">
      <p>上次刮削未完成，是否继续刮削剩余任务？</p>
      <p v-if="resumeInfo && !resumeInfo.first_in_scan_dirs" class="warn">
        ⚠️ 剩余任务文件（{{ resumeInfo.first_path }}）不在当前待刮削目录中，请确认成功/失败输出目录配置正确！
      </p>
      <template #footer>
        <el-button @click="resumeDialog = false">取消</el-button>
        <el-button type="primary" plain @click="resumeDialog = false; doStart('default')">从头刮削</el-button>
        <el-button type="primary" @click="onResume">继续刮削剩余任务（{{ resumeInfo?.count }}）</el-button>
      </template>
    </el-dialog>

    <!-- NFO 查看 -->
    <el-dialog v-model="nfoDialog" :title="nfoPath" width="720px" top="6vh">
      <pre class="nfo-pre">{{ nfoText }}</pre>
    </el-dialog>

    <!-- 右键菜单 -->
    <teleport to="body">
      <div
        v-if="menu.show"
        class="ctx-menu"
        :style="{ left: menu.x + 'px', top: menu.y + 'px' }"
        @click.stop
      >
        <div class="ctx-item" @click="onPlay">▶ 播放</div>
        <div class="ctx-item" @click="onOpenNfo">📄 查看 NFO</div>
        <div class="ctx-item" @click="onRescrape">🔄 按文件重刮</div>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
.scrape-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 16px;
}
.media-path-box {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  margin-right: 12px;
}
.media-label {
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}
.media-path-box .dir-picker {
  flex: 1;
  min-width: 0;
}
.media-path-box :deep(.picker-input .el-input__inner) {
  font-size: 12px;
}
.hint {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.content {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.results {
  flex: 1.2;
  min-width: 0;
}
.detail {
  flex: 1;
  min-width: 380px;
}
.detail-head {
  display: flex;
  gap: 16px;
}
.images {
  display: flex;
  gap: 8px;
}
.poster {
  width: 150px;
  height: 210px;
  border-radius: 6px;
  background: #f0f2f5;
}
.thumb {
  width: 200px;
  height: 150px;
  border-radius: 6px;
  background: #f0f2f5;
}
.img-slot {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  font-size: 12px;
}
.number {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--el-color-primary);
}
.outline {
  max-height: 120px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 12px;
}
.nfo-pre {
  max-height: 65vh;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.ctx-menu {
  position: fixed;
  z-index: 3000;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
  min-width: 140px;
}
.ctx-item {
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
}
.ctx-item:hover {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.warn {
  color: var(--el-color-danger);
  font-size: 13px;
}
.progress-pane {
  padding: 16px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: calc(100vh - 320px);
}
.current-file {
  margin: 0;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  color: #606266;
}
.eta {
  color: var(--el-color-primary);
  font-size: 13px;
}
.note {
  margin-top: auto;
  color: #909399;
  font-size: 12px;
  line-height: 1.7;
}
</style>
