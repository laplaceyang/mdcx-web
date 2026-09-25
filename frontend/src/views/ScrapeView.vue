<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, mediaUrl, videoUrl, type ActiveItem, type ResultItem, type ResumeInfo } from '../api/client'
import { useScrapeStore } from '../stores/scrape'
import DirPicker from '../components/DirPicker.vue'
import ScrapeCard from '../components/ScrapeCard.vue'
import ManualScrapeDialog from '../components/ManualScrapeDialog.vue'

const scrape = useScrapeStore()
// 手动刮削对话框（与软件工具-单文件刮削共用组件）
const scrapeDialogRef = ref<InstanceType<typeof ManualScrapeDialog>>()

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

const activeTab = ref<'all' | 'succ' | 'fail' | 'progress'>('all')
const selected = ref<ResultItem | null>(null)
const resumeDialog = ref(false)
const resumeInfo = ref<ResumeInfo | null>(null)
const nfoDialog = ref(false)
const nfoText = ref('')
const nfoPath = ref('')

const succCount = computed(() => scrape.results.filter((r) => r.status === 'succ').length)
const failCount = computed(() => scrape.results.filter((r) => r.status === 'fail').length)

// ===== 本次任务实时进度（donePercent 用 store 的共享口径，与底栏一致） =====
const elapsedText = computed(() => {
  const s = Math.max(0, Math.round(scrape.status.elapsed))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
})

// ===== 刮削中卡片：在途条目快照轮询（页签可见且任务活跃时 1s 一次） =====
const activeItems = ref<ActiveItem[]>([])
let activeTimer: number | undefined

async function pollActive() {
  try {
    activeItems.value = (await api.scrapeActive()).items
  } catch {
    /* 服务未就绪时静默 */
  }
}

watch(
  [activeTab, () => scrape.running, () => scrape.stopping],
  ([tab, running, stopping]) => {
    window.clearInterval(activeTimer)
    activeTimer = undefined
    if (tab !== 'progress') return
    void pollActive()
    if (running || stopping) activeTimer = window.setInterval(pollActive, 1000)
  },
  { immediate: true },
)
onUnmounted(() => window.clearInterval(activeTimer))

function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分 ${s % 60} 秒`
  return `${Math.floor(m / 60)} 时 ${m % 60} 分`
}

function fmtClock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

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

// ===== 成功页签：与「刮削中」一致的卡片视图 =====
interface SuccCard {
  key: string
  item: ResultItem
  number: string
  title: string
  actors: string
  release: string
  score: string
  image: string | null
  filePath: string
}

function toSuccCard(item: ResultItem): SuccCard {
  const row = toRow(item)
  const filePath = String(item.show?.file_info?.file_path ?? '')
  return {
    key: `${item.real_number}|${filePath}`,
    item,
    number: row.number,
    title: row.title,
    actors: row.actor,
    release: row.release,
    score: String((item.show?.data as Record<string, unknown>)?.score ?? ''),
    image: mediaUrl(item.show?.other?.poster_path || item.show?.other?.thumb_path),
    filePath,
  }
}

// 大批量刮削时一次性渲染上万张卡片会卡顿，先渲染前 succLimit 张
const succLimit = ref(200)
const succCardsAll = computed(() => scrape.results.filter((r) => r.status === 'succ').map(toSuccCard))
const succCards = computed(() => succCardsAll.value.slice(0, succLimit.value))
const succRemain = computed(() => succCardsAll.value.length - succCards.value.length)

// ===== 失败页签：与成功一致的卡片视图 + 失败原因 + 重刮操作 =====
interface FailCard {
  key: string
  item: ResultItem
  number: string
  fileName: string
  filePath: string
  reason: string
}

const failLimit = ref(200)
const failCardsAll = computed(() =>
  scrape.results
    .filter((r) => r.status === 'fail')
    .map((item) => {
      const fi = (item.show?.file_info ?? {}) as Record<string, unknown>
      const filePath = String(fi.file_path ?? '')
      const fileName =
        String(fi.file_show_name ?? '') || filePath.replace(/\\/g, '/').split('/').pop() || filePath
      return {
        key: `${item.real_number}|${filePath}`,
        item,
        number: item.real_number || '未知番号',
        fileName,
        filePath,
        reason: String(item.show?.other?.fail_reason ?? '') || '未知错误',
      }
    }),
)
const failCards = computed(() => failCardsAll.value.slice(0, failLimit.value))
const failRemain = computed(() => failCardsAll.value.length - failCards.value.length)

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
  succLimit.value = 200
  failLimit.value = 200
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

// 失败卡片的手动刮削：人工填元数据，NFO/封面/视频整理进番号目录；
// 番号提取失败时回退用任务识别出的番号
function onManualScrape(c: FailCard) {
  scrapeDialogRef.value?.open({ mode: 'scrape', videoPath: c.filePath, number: c.item.real_number || '' })
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
      <span class="hint">单击卡片看详情；右键卡片：播放 / 查看 NFO / 重刮</span>
    </el-card>

    <div class="content">
      <el-card class="results" shadow="never">
        <el-tabs v-model="activeTab">
          <el-tab-pane name="all">
            <template #label>全部</template>
            <div class="all-pane">
              <el-progress
                :percentage="scrape.donePercent"
                :stroke-width="16"
                :status="scrape.running ? undefined : scrape.donePercent >= 100 ? 'success' : undefined"
              />
              <el-descriptions :column="3" size="small" border class="stat">
                <el-descriptions-item label="任务总数">{{ scrape.status.counts.total }}</el-descriptions-item>
                <el-descriptions-item label="已完成">{{ scrape.status.counts.done }}</el-descriptions-item>
                <el-descriptions-item label="刮削中">{{ scrape.status.counts.in_progress }}</el-descriptions-item>
                <el-descriptions-item label="成功">{{ scrape.status.counts.succ }}</el-descriptions-item>
                <el-descriptions-item label="失败">{{ scrape.status.counts.fail }}</el-descriptions-item>
                <el-descriptions-item label="已用时间">{{ elapsedText }}</el-descriptions-item>
              </el-descriptions>
              <pre class="current-file">{{
                scrape.currentFileLabel || (scrape.running ? '（正在分配任务…）' : '（当前没有正在刮削的任务）')
              }}</pre>
              <div v-if="scrape.scrapeInfo" class="eta-line">{{ scrape.scrapeInfo }}</div>
              <div class="note">
                统计为「本次任务」口径：每次点「开始刮削」都会清零重新累计；成功/失败按视频文件计数，
                同一影片的多个分部（multi-part）会合并进输出目录的同一个文件夹。历史刮削成果以输出目录为准，本页不保留。
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane name="succ">
            <template #label>成功 ({{ succCount }})</template>
            <div class="succ-pane">
              <div v-if="succCards.length" class="cards">
                <ScrapeCard
                  v-for="c in succCards"
                  :key="c.key"
                  :number="c.number"
                  :title="c.title"
                  :title-fallback="c.filePath"
                  :actors="c.actors"
                  :image="c.image"
                  placeholder="暂无封面"
                  :footer="c.filePath"
                  :selected="selected === c.item"
                  @click="onSelectRow(c.item)"
                  @contextmenu="(ev: MouseEvent) => onRowContext(ev, c.item)"
                >
                  <template #meta>
                    <span v-if="c.release">📅 {{ c.release }}</span>
                    <span v-if="c.score">⭐ {{ c.score }}</span>
                  </template>
                </ScrapeCard>
              </div>
              <el-empty v-else description="暂无成功结果" :image-size="80" />
              <div v-if="succRemain > 0" class="load-more">
                <el-button text type="primary" @click="succLimit += 500">
                  显示更多（还有 {{ succRemain }} 个）
                </el-button>
              </div>
              <div v-if="succCards.length" class="note">
                单击卡片查看详情，右键卡片：播放 / 查看 NFO / 重刮。历史刮削成果以输出目录为准，本页仅保留本次任务结果。
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane name="progress">
            <template #label>刮削中 ({{ scrape.status.counts.in_progress }})</template>
            <div class="progress-pane">
              <div v-if="activeItems.length" class="cards">
                <ScrapeCard
                  v-for="it in activeItems"
                  :key="it.file_path"
                  :number="it.number || '识别番号中…'"
                  :title="it.title"
                  :title-fallback="it.show_path"
                  :actors="it.actors"
                  :image="mediaUrl(it.poster || it.thumb)"
                  placeholder="等待封面"
                  :footer="it.last_log || '正在启动…'"
                  :footer-tooltip="(it.logs || []).join('\n')"
                >
                  <template #meta>
                    <span>⏱ {{ fmtDuration(it.elapsed) }}</span>
                    <span>开始于 {{ fmtClock(it.started_at) }}</span>
                  </template>
                </ScrapeCard>
              </div>
              <el-empty
                v-else
                :description="scrape.running ? '正在分配任务…' : '当前没有正在刮削的任务'"
                :image-size="80"
              />
            </div>
          </el-tab-pane>
          <el-tab-pane name="fail">
            <template #label>失败 ({{ failCount }})</template>
            <div class="fail-pane">
              <div v-if="failCards.length" class="cards">
                <ScrapeCard
                  v-for="c in failCards"
                  :key="c.key"
                  :number="c.number"
                  :title="c.fileName"
                  :actors="''"
                  :image="null"
                  placeholder="无封面"
                  :error="c.reason"
                  :footer="c.filePath"
                  :selected="selected === c.item"
                  @click="onSelectRow(c.item)"
                  @contextmenu="(ev: MouseEvent) => onRowContext(ev, c.item)"
                >
                  <template #meta>
                    <el-button size="small" text type="primary" @click.stop="selected = c.item; onRescrape()">
                      🔄 重刮
                    </el-button>
                    <el-button size="small" text type="primary" @click.stop="onManualScrape(c)">
                      ✍️ 手动刮削
                    </el-button>
                  </template>
                </ScrapeCard>
              </div>
              <el-empty v-else description="暂无失败结果" :image-size="80" />
              <div v-if="failRemain > 0" class="load-more">
                <el-button text type="primary" @click="failLimit += 500">
                  显示更多（还有 {{ failRemain }} 个）
                </el-button>
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

    <!-- 手动刮削（失败卡片入口，与软件工具-单文件刮削共用） -->
    <ManualScrapeDialog ref="scrapeDialogRef" />

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
.all-pane,
.succ-pane,
.fail-pane,
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
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  color: #606266;
}
.eta-line {
  color: var(--el-color-primary);
  font-size: 13px;
}
.load-more {
  display: flex;
  justify-content: center;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 10px;
  align-content: start;
}
.note {
  margin-top: auto;
  color: #909399;
  font-size: 12px;
  line-height: 1.7;
}
</style>
