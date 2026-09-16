<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, ApiError } from '../api/client'
import { useScrapeStore } from '../stores/scrape'
import DirPicker from '../components/DirPicker.vue'
import MediaFilePicker from '../components/MediaFilePicker.vue'

const scrape = useScrapeStore()

// 单文件刮削
const singleFile = ref('')
const singleUrl = ref('')
const siteOptions = ref<{ site: string; url: string }[]>([])
// 软链接
const symlinkCopyNfo = ref(false)
// 封面补图
const backfillNumbers = ref('')
const backfillOverwrite = ref(false)
const backfillWatermark = ref(false)
// Gfriends
const gfriendsPath = ref('')
// 演员库
const aliasSource = ref('tmdb')
const aliasAll = ref(false)
const actorDbOffset = ref(0)
const actorDbLimit = ref(0)
const actorDbNfoDir = ref('')
// 缓存管理
const cacheStats = ref<Record<string, any> | null>(null)
const cacheFailed = ref<import('../api/client').CacheFailedItem[]>([])
const failedSelection = ref<import('../api/client').CacheFailedItem[]>([])

const running = ref<string[]>([])
let statusTimer: number | undefined

async function refreshStatus() {
  try {
    running.value = (await api.toolsStatus()).running
  } catch {
    /* ignore */
  }
}

function isRunning(name: string): boolean {
  return running.value.some((r) => r.startsWith(name))
}

async function run(name: string, fn: () => Promise<unknown>) {
  try {
    await fn()
    ElMessage.success(`「${name}」已开始，进度见日志页`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
  setTimeout(refreshStatus, 300)
}

async function onSingleScrape() {
  if (!singleFile.value || !singleUrl.value) {
    ElMessage.warning('请填写文件路径和番号网址')
    return
  }
  await run('单文件刮削', () => api.singleScrape(singleFile.value, singleUrl.value))
}

async function onCoverBackfill() {
  const numbers = backfillNumbers.value.split(/\s+/).filter(Boolean)
  if (!numbers.length) {
    ElMessage.warning('请输入番号')
    return
  }
  await run('封面补图', () => api.toolsCoverBackfill(numbers, backfillOverwrite.value, backfillWatermark.value))
}

async function onActorDb(task: string, extra: Record<string, unknown> = {}) {
  await run(task, () => api.toolsActorDb(task, extra))
}

// 上传图片补图：共用番号列表的首个番号（与开始补图一致），不单独设输入框
function firstBackfillNumber(): string {
  const first = backfillNumbers.value.split(/\s+/).filter(Boolean)[0] ?? ''
  if (first.includes('/')) return '' // 是文件路径不是番号
  return first
}

async function onUploadCover(uploadFile: { raw?: File }) {
  const raw = uploadFile.raw
  if (!raw) return
  const number = firstBackfillNumber()
  if (!number) {
    ElMessage.warning('请先在上方填写番号（如 FNS-248）')
    return
  }
  try {
    const d = await api.coverBackfillUpload(number, raw, backfillOverwrite.value)
    ElMessage.success(`上传补图完成：${d.thumb} / ${d.poster}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

// 翻译测试
const translateMode = ref<'nfo' | 'text' | 'edit'>('text')
const translateNfo = ref('')
const translateText = ref('')
const translateDialog = ref(false)
const translateLoading = ref(false)
const translateResult = ref('')
const translateNfoPath = ref('')
const translateLog = ref('')
const translateFieldInfo = ref<Record<string, any> | null>(null)
// NFO 直接编辑
const editNfoPath = ref('')
const editNfoContent = ref('')
const editLoading = ref(false)

function copyTranslateResult() {
  navigator.clipboard
    .writeText(translateResult.value)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}

function downloadTranslateNfo() {
  const blob = new Blob([translateResult.value], { type: 'text/xml;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = translateNfoPath.value.split('/').pop() || 'translated.nfo'
  a.click()
  URL.revokeObjectURL(a.href)
}

async function onOverwriteSave() {
  try {
    await ElMessageBox.confirm(`将覆盖保存到 ${translateNfoPath.value}（原文件自动备份为 .bak），确定？`, '覆盖保存', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const d = await api.translateTestSave(translateNfoPath.value, translateResult.value)
    ElMessage.success(`已覆盖保存，原文件备份为 ${d.bak}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function startTranslate() {
  if (translateMode.value === 'edit') return
  if (translateMode.value === 'nfo' && !translateNfo.value) {
    ElMessage.warning('请先选择 NFO 文件')
    return
  }
  if (translateMode.value === 'text' && !translateText.value.trim()) {
    ElMessage.warning('请输入要翻译的内容')
    return
  }
  translateDialog.value = true
  translateLoading.value = true
  translateResult.value = ''
  try {
    const d = await api.translateTest(
      translateMode.value,
      translateMode.value === 'nfo' ? { path: translateNfo.value } : { text: translateText.value },
    )
    translateResult.value = d.content
    translateNfoPath.value = d.path ?? ''
    translateLog.value = d.log ?? ''
    translateFieldInfo.value = d.field_info ?? null
  } catch (e) {
    translateDialog.value = false
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    translateLoading.value = false
  }
}

// NFO 直接编辑：读取原文 → 编辑 → 保存（.bak 备份）
async function readNfoForEdit() {
  if (!editNfoPath.value) {
    ElMessage.warning('请先选择 NFO 文件')
    return
  }
  editLoading.value = true
  try {
    const resp = await fetch(`/api/media/file?path=${encodeURIComponent(editNfoPath.value)}`)
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail ?? resp.statusText)
    editNfoContent.value = await resp.text()
    ElMessage.success('已读取，可直接编辑后保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    editLoading.value = false
  }
}

async function saveEditedNfo() {
  if (!editNfoPath.value || !editNfoContent.value.trim()) {
    ElMessage.warning('没有可保存的内容')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将覆盖保存到 ${editNfoPath.value}（原文件自动备份为 .bak），确定？`,
      '保存 NFO',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const d = await api.translateTestSave(editNfoPath.value, editNfoContent.value)
    ElMessage.success(`已保存，原文件备份为 ${d.bak}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

// 创建 NFO：表单填写 → /api/nfo/create 按正常流程元素顺序生成 .nfo 文件
const createDialog = ref(false)
const createLoading = ref(false)
const createTranslating = ref<'' | 'title' | 'outline'>('')
const createResult = ref<{ path: string; content: string; covers?: { thumb: string; poster: string }; video?: string } | null>(null)
const createCoverFile = ref<File | null>(null)
// scrape 模式（单文件刮削 → 手动刮削）：落盘到 {目录}/{番号}/，视频移入并改名番号
const createMode = ref<'create' | 'scrape'>('create')
const scrapeVideoPath = ref('')
const createForm = ref({
  number: '',
  release: '',
  title: '',
  originaltitle: '',
  originalplot: '',
  plot: '',
  actors: '',
  series: '',
  studio: '',
  publisher: '',
  genres: '',
  countrycode: 'JP',
})
const createDir = ref('')
const createFilename = ref('')
const filenameTouched = ref(false)
const titleTouched = ref(false)
const plotTouched = ref(false)

// 成功输出目录（多路径时取第一个），作为创建 NFO 的默认保存目录
let successDirCache = ''
async function defaultCreateDir(): Promise<string> {
  if (successDirCache) return successDirCache
  try {
    const d = await api.config()
    successDirCache = String(d.config.success_output_folder ?? '').split('|')[0].trim()
  } catch {
    /* 拉取失败留空，后端会回退到成功输出目录 */
  }
  return successDirCache
}

function openCreateDialog(mode: 'create' | 'scrape' = 'create') {
  createMode.value = mode
  scrapeVideoPath.value = ''
  createForm.value = {
    number: '',
    release: '',
    title: '',
    originaltitle: '',
    originalplot: '',
    plot: '',
    actors: '',
    series: '',
    studio: '',
    publisher: '',
    genres: '',
    countrycode: 'JP',
  }
  filenameTouched.value = false
  titleTouched.value = false
  plotTouched.value = false
  createResult.value = null
  createCoverFile.value = null
  createDialog.value = true
  defaultCreateDir().then((dir) => {
    if (createDialog.value && !createDir.value) createDir.value = dir
  })
}

// 文件名默认跟随番号，手动改过后不再跟随
function onCreateNumberInput() {
  if (!filenameTouched.value) createFilename.value = createForm.value.number.trim()
}

// originaltitle/originalplot → title/plot：复用正常流程的按字段翻译；force=手动按钮时强制覆盖
async function translateCreateField(field: 'title' | 'outline', force: boolean) {
  const src = field === 'title' ? createForm.value.originaltitle : createForm.value.originalplot
  if (!src.trim()) {
    if (force) ElMessage.warning(field === 'title' ? '请先填写原标题' : '请先填写原简介')
    return
  }
  if (createTranslating.value === field) return
  if (!force && (field === 'title' ? titleTouched.value : plotTouched.value)) return // 手动改过目标字段则不覆盖
  createTranslating.value = field
  try {
    const d = await api.translateTest('text', { text: src, field })
    const translated = (d.content ?? '').trim()
    if (field === 'title') {
      const n = createForm.value.number.trim()
      createForm.value.title = n && !translated.startsWith(n) ? `${n} ${translated}` : translated
      titleTouched.value = false
    } else {
      createForm.value.plot = translated
      plotTouched.value = false
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    createTranslating.value = ''
  }
}

function splitCreateList(text: string): string[] {
  return text
    .split(/[,，\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function onCreateCoverPicked(uploadFile: { raw?: File }) {
  if (uploadFile.raw) createCoverFile.value = uploadFile.raw
}

// 手动刮削：复用创建 NFO 表单，用单文件刮削 tab 选中的视频
async function onManualScrape() {
  if (!singleFile.value) {
    ElMessage.warning('请先选择视频文件')
    return
  }
  openCreateDialog('scrape')
  scrapeVideoPath.value = singleFile.value
  // 番号默认值：按正常流程规则从文件名自动提取；提取不到留空手填
  try {
    const d = await api.extractNumber(singleFile.value)
    if (d.number) {
      createForm.value.number = d.number
      onCreateNumberInput()
    }
  } catch {
    /* 提取失败不阻塞，手动填写 */
  }
}

async function onCreateNfo(overwrite = false) {
  const f = createForm.value
  const scraping = createMode.value === 'scrape'
  if (scraping && !f.number.trim()) {
    ElMessage.warning('请填写番号（用作文件夹和视频文件名）')
    return
  }
  if (!createFilename.value.trim() && !f.number.trim()) {
    ElMessage.warning('请填写番号或文件名')
    return
  }
  createLoading.value = true
  try {
    const subfolder = scraping ? f.number.trim() : ''
    const d = await api.nfoCreate({
      dir: createDir.value,
      subfolder,
      filename: createFilename.value,
      overwrite,
      fields: {
        number: f.number.trim(),
        release: f.release,
        title: f.title.trim(),
        originaltitle: f.originaltitle.trim(),
        originalplot: f.originalplot.trim(),
        plot: f.plot.trim(),
        actors: splitCreateList(f.actors),
        series: f.series.trim(),
        studio: f.studio.trim(),
        publisher: f.publisher.trim(),
        genres: splitCreateList(f.genres),
        countrycode: f.countrycode.trim(),
      },
    })
    createResult.value = { path: d.path, content: d.content }
    // 补图：与 NFO 同目录、基础名同 NFO 文件名（后端与 NFO 命名共用同一清洗规则）
    if (createCoverFile.value) {
      try {
        const name = createFilename.value.trim() || f.number.trim()
        const c = await api.nfoCreateCover(name, createDir.value, subfolder, createCoverFile.value)
        createResult.value = { ...createResult.value!, covers: { thumb: c.thumb, poster: c.poster } }
      } catch (e) {
        ElMessage.error(`NFO 已创建，但补图失败：${e instanceof Error ? e.message : String(e)}`)
      }
    }
    // 手动刮削：视频移入番号目录并改名为番号（保留原扩展名）
    if (scraping && scrapeVideoPath.value) {
      try {
        const mv = await api.nfoMoveVideo(scrapeVideoPath.value, createDir.value, subfolder, f.number.trim(), overwrite)
        createResult.value = { ...createResult.value!, video: mv.path }
      } catch (e) {
        ElMessage.error(`NFO 已创建，但视频移动失败：${e instanceof Error ? e.message : String(e)}`)
      }
    }
    ElMessage.success(scraping ? `刮削完成：${d.path}` : `NFO 已创建：${d.path}`)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && !overwrite) {
      try {
        await ElMessageBox.confirm(`${e.message}，是否覆盖？`, '文件已存在', { type: 'warning' })
        await onCreateNfo(true)
      } catch {
        /* 取消覆盖 */
      }
    } else {
      ElMessage.error(e instanceof Error ? e.message : String(e))
    }
  } finally {
    createLoading.value = false
  }
}

function downloadCreatedNfo() {
  if (!createResult.value) return
  const blob = new Blob([createResult.value.content], { type: 'text/xml;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = createResult.value.path.split('/').pop() || 'created.nfo'
  a.click()
  URL.revokeObjectURL(a.href)
}

function copyCreatedNfo() {
  if (!createResult.value) return
  navigator.clipboard
    .writeText(createResult.value.content)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}

function onBackfillFilesPicked(paths: string | string[]) {
  const list = Array.isArray(paths) ? paths : [paths]
  const merged = [...backfillNumbers.value.split(/\s+/).filter(Boolean), ...list]
  backfillNumbers.value = Array.from(new Set(merged)).join(' ')
}

async function refreshCache() {
  try {
    const d = await api.cacheStats()
    cacheStats.value = d.stats
    cacheFailed.value = d.failed
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onCacheDeleteSelected() {
  if (!failedSelection.value.length) {
    ElMessage.warning('请先选中要重置的记录')
    return
  }
  await api.cacheDelete(failedSelection.value.map((f) => f.file_path))
  ElMessage.success(`已重置 ${failedSelection.value.length} 条记录`)
  await refreshCache()
}

async function onCacheClear() {
  try {
    await ElMessageBox.confirm('将清空全部刮削缓存状态，下次刮削将重新处理所有文件。已生成的 NFO 不会被删除。确认清空？', '清空缓存', {
      type: 'warning',
    })
  } catch {
    return
  }
  await api.cacheClear()
  ElMessage.success('缓存已清空')
  await refreshCache()
}

function onExportCache() {
  window.open(api.cacheExport(), '_blank')
}

onMounted(() => {
  refreshStatus()
  void refreshCache()
  statusTimer = window.setInterval(refreshStatus, 3000)
  // 站点 URL（含用户自定义），供单文件刮削的番号网址下拉选择
  api
    .configSites()
    .then((d) => (siteOptions.value = d.sites))
    .catch(() => {})
})
onActivated(refreshStatus)
</script>

<template>
  <div class="tools-view">
    <el-alert type="info" :closable="false" class="tip">
      工具执行日志实时推送到「软件日志」页；运行中的工具显示
      <el-tag v-for="r in running" :key="r" size="small" class="ml">{{ r }}</el-tag>
    </el-alert>

    <el-row :gutter="12">
      <el-col :span="12">
        <el-card shadow="never" header="🎯 单文件刮削">
          <div class="labeled-row">
            <span class="row-label">视频文件</span>
            <MediaFilePicker v-model="singleFile" placeholder="从配置的媒体目录中选择视频文件" />
          </div>
          <div class="labeled-row">
            <span class="row-label">番号网址</span>
            <el-select
              v-model="singleUrl"
              class="grow"
              filterable
              allow-create
              default-first-option
              placeholder="选择配置的站点，或直接输入完整网址"
            >
              <el-option v-for="s in siteOptions" :key="s.site" :label="`${s.site} · ${s.url}`" :value="s.url" />
            </el-select>
          </div>
          <div class="btn-row">
            <el-button type="primary" :disabled="scrape.running || scrape.stopping" @click="onSingleScrape">
              刮削
            </el-button>
            <el-button plain @click="onManualScrape">手动刮削</el-button>
          </div>
          <p class="upload-hint">手动刮削：打开 NFO 表单人工填写元数据，完成后视频与 NFO/封面一起整理进以番号命名的文件夹</p>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" header="🔗 软链接 / 移动 / 字幕">
          <div class="btn-row">
            <el-checkbox v-model="symlinkCopyNfo" label="同时复制 NFO" />
            <el-button :disabled="isRunning('软链接创建')" @click="run('软链接创建', () => api.toolsSymlink(symlinkCopyNfo))">
              网盘软链接创建
            </el-button>
          </div>
          <div class="btn-row">
            <el-button :disabled="isRunning('视频/字幕移动')" @click="run('视频/字幕移动', api.toolsMoveVideos)">
              视频/字幕移动到 Movie_moved
            </el-button>
            <el-button :disabled="isRunning('批量字幕添加')" @click="run('批量字幕添加', api.toolsSubtitle)">
              批量添加字幕
            </el-button>
          </div>
          <div class="btn-row">
            <el-button :disabled="isRunning('extras')" @click="run('extras 剧照', () => api.toolsExtras('extrafanart_copy', 'add'))">
              创建剧照副本
            </el-button>
            <el-button :disabled="isRunning('extras')" @click="run('extras 剧照', () => api.toolsExtras('extrafanart_copy', 'del'))">
              删除剧照副本
            </el-button>
            <el-button :disabled="isRunning('extras')" @click="run('extras 主题视频', () => api.toolsExtras('theme', 'add'))">
              创建主题视频
            </el-button>
            <el-button :disabled="isRunning('extras')" @click="run('extras 主题视频', () => api.toolsExtras('theme', 'del'))">
              删除主题视频
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="mt">
      <el-col :span="12">
        <el-card shadow="never" header="🖼️ 封面补图">
          <div class="labeled-row">
            <span class="row-label">番号列表</span>
            <el-input
              v-model="backfillNumbers"
              type="textarea"
              :rows="2"
              class="grow"
              placeholder="番号列表（空格分隔），如：FNS-248 DVAJ-754"
            />
          </div>
          <div class="labeled-row">
            <span class="row-label">选择文件</span>
            <MediaFilePicker
              :model-value="''"
              multiple
              placeholder="也可从配置的媒体目录中选择视频文件（可多选）"
              @update:model-value="onBackfillFilesPicked"
            />
          </div>
          <div class="btn-row">
            <el-checkbox v-model="backfillOverwrite" label="覆盖已有图片" />
            <el-checkbox v-model="backfillWatermark" label="加水印" />
            <el-button type="primary" :disabled="isRunning('封面补图')" @click="onCoverBackfill">开始补图</el-button>
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept="image/jpeg,image/png,image/webp"
              :on-change="onUploadCover"
            >
              <el-button plain>📤 上传图片补图</el-button>
            </el-upload>
          </div>
          <p class="upload-hint">上传补图使用「番号列表」的第一个番号，选择本地图后立即保存到成功输出目录：横图自动裁竖版海报</p>
        </el-card>

        <el-card shadow="never" header="🌐 翻译测试 / NFO 编辑" class="mt">
          <div class="translate-header mb">
            <el-radio-group v-model="translateMode">
              <el-radio-button value="text">直接输入内容</el-radio-button>
              <el-radio-button value="nfo">NFO 翻译</el-radio-button>
              <el-radio-button value="edit">NFO 直接编辑</el-radio-button>
            </el-radio-group>
            <el-button type="primary" plain @click="openCreateDialog">🆕 创建 NFO</el-button>
          </div>

          <template v-if="translateMode === 'nfo'">
            <div class="labeled-row">
              <span class="row-label">NFO 文件</span>
              <MediaFilePicker
                v-model="translateNfo"
                exts=".nfo"
                placeholder="从媒体目录中选择要翻译的 NFO 文件"
              />
            </div>
            <el-button type="primary" :loading="translateLoading" @click="startTranslate">翻译</el-button>
          </template>

          <template v-else-if="translateMode === 'edit'">
            <div class="labeled-row">
              <span class="row-label">NFO 文件</span>
              <MediaFilePicker v-model="editNfoPath" exts=".nfo" placeholder="选择要直接编辑的 NFO 文件" />
              <el-button :loading="editLoading" :disabled="!editNfoPath" @click="readNfoForEdit">读取</el-button>
            </div>
            <el-input
              v-if="editNfoContent"
              v-model="editNfoContent"
              type="textarea"
              :autosize="{ minRows: 10, maxRows: 22 }"
              class="mb"
            />
            <el-button v-if="editNfoContent" type="warning" @click="saveEditedNfo">
              保存（原文件备份 .bak）
            </el-button>
          </template>

          <template v-else>
            <el-input
              v-model="translateText"
              type="textarea"
              :rows="3"
              placeholder="输入要翻译的标题或简介（按设置里的翻译引擎和目标语言执行正常流程）"
              class="mb"
            />
            <el-button type="primary" :loading="translateLoading" @click="startTranslate">翻译</el-button>
          </template>
        </el-card>
    <!-- 翻译测试结果弹窗（结果可直接编辑，保存/复制用编辑后的内容） -->
    <el-dialog v-model="translateDialog" title="翻译结果（可直接编辑）" width="780px" top="6vh" :close-on-click-modal="false">
      <div v-loading="translateLoading" class="translate-result">
        <el-input
          v-if="!translateLoading && translateResult"
          v-model="translateResult"
          type="textarea"
          :autosize="{ minRows: 8, maxRows: 20 }"
        />
        <div v-if="!translateLoading && !translateResult" class="empty">（无结果）</div>
      </div>
      <div v-if="translateFieldInfo" class="field-info">
        字段配置：标题语言 {{ translateFieldInfo.title_language }}（{{ translateFieldInfo.title_translate ? '开翻译' : '关翻译' }}）、
        简介语言 {{ translateFieldInfo.outline_language }}（{{ translateFieldInfo.outline_translate ? '开翻译' : '关翻译' }}）、
        翻译引擎：{{ (translateFieldInfo.translate_by as string[]).join(' → ') }}
        <span v-if="translateFieldInfo.title_language === 'jp'" class="warn">
          ⚠️ 标题语言设为日文 = 保留原文不翻译（与正常刮削流程一致）
        </span>
      </div>
      <pre v-if="translateLog" class="translate-log">{{ translateLog }}</pre>
      <template #footer>
        <el-button @click="copyTranslateResult" :disabled="!translateResult">复制</el-button>
        <template v-if="translateMode === 'nfo' && translateResult">
          <el-button @click="downloadTranslateNfo">下载 NFO</el-button>
          <el-button type="warning" @click="onOverwriteSave">覆盖保存（原文件备份 .bak）</el-button>
        </template>
        <el-button @click="translateDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 翻译测试结果弹窗结束 -->

    <!-- 创建 NFO 表单弹窗 -->
    <el-dialog v-model="createDialog" :title="createMode === 'scrape' ? '手动刮削' : '创建 NFO'" width="720px" top="5vh" :close-on-click-modal="false">
      <div v-loading="createLoading">
        <el-alert
          v-if="createResult"
          type="success"
          :closable="false"
          class="mb"
          :title="`${createMode === 'scrape' ? '已刮削' : '已创建'}：${createResult.path}`"
        >
          <div v-if="createResult.covers">
            封面图：{{ createResult.covers.thumb }}<br />{{ createResult.covers.poster }}
          </div>
          <div v-if="createResult.video">视频：{{ createResult.video }}</div>
        </el-alert>
        <template v-if="!createResult">
          <el-form label-width="70px">
            <el-row :gutter="10">
              <el-col :span="12">
                <el-form-item label="番号">
                  <el-input v-model="createForm.number" placeholder="如 OFJE-536" @input="onCreateNumberInput" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="发行日期">
                  <el-input v-model="createForm.release" placeholder="YYYY-MM-DD，可留空" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="原标题">
              <el-input
                v-model="createForm.originaltitle"
                placeholder="填写后自动翻译，生成带番号的标题"
                @blur="translateCreateField('title', false)"
              >
                <template #append>
                  <el-button :loading="createTranslating === 'title'" @click="translateCreateField('title', true)">
                    翻译
                  </el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="createForm.title" placeholder="留空时可由原标题翻译生成" @input="titleTouched = true" />
            </el-form-item>
            <el-form-item label="原简介">
              <div class="stack-full">
                <el-input
                  v-model="createForm.originalplot"
                  type="textarea"
                  :rows="2"
                  placeholder="填写后自动翻译，生成简介"
                  @blur="translateCreateField('outline', false)"
                />
                <div class="translate-btn-row">
                  <el-button
                    size="small"
                    text
                    type="primary"
                    :loading="createTranslating === 'outline'"
                    @click="translateCreateField('outline', true)"
                  >
                    翻译
                  </el-button>
                </div>
              </div>
            </el-form-item>
            <el-form-item label="简介">
              <el-input
                v-model="createForm.plot"
                type="textarea"
                :rows="3"
                placeholder="可选；留空时可由原简介翻译生成"
                @input="plotTouched = true"
              />
            </el-form-item>
            <el-divider content-position="left" style="margin: 6px 0 14px">详细信息（可选）</el-divider>
            <el-form-item label="演员">
              <el-input v-model="createForm.actors" type="textarea" :rows="2" placeholder="多个演员用换行或逗号分隔" />
            </el-form-item>
            <el-row :gutter="10">
              <el-col :span="8">
                <el-form-item label="系列">
                  <el-input v-model="createForm.series" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="片商">
                  <el-input v-model="createForm.studio" placeholder="写入 studio/maker" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="发行">
                  <el-input v-model="createForm.publisher" placeholder="写入 publisher/label" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="10">
              <el-col :span="16">
                <el-form-item label="标签">
                  <el-input v-model="createForm.genres" placeholder="多个标签用逗号分隔（写入 genre）" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="国家">
                  <el-select v-model="createForm.countrycode" filterable allow-create default-first-option style="width: 100%">
                    <el-option label="JP" value="JP" />
                    <el-option label="US" value="US" />
                    <el-option label="CN" value="CN" />
                    <el-option label="KR" value="KR" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-divider content-position="left" style="margin: 6px 0 14px">保存位置</el-divider>
            <el-form-item label="目录">
              <div class="stack-full">
                <DirPicker v-model="createDir" placeholder="留空时保存到成功输出目录" />
                <p v-if="createMode === 'scrape'" class="upload-hint">
                  将在该目录下创建以番号命名的文件夹，NFO/封面/视频都放进去
                </p>
              </div>
            </el-form-item>
            <el-form-item label="文件名">
              <el-input v-model="createFilename" placeholder="默认使用番号，自动补 .nfo" @input="filenameTouched = true">
                <template #append>.nfo</template>
              </el-input>
            </el-form-item>
            <el-form-item label="封面图">
              <div class="stack-full">
                <el-upload
                  :auto-upload="false"
                  :show-file-list="false"
                  accept="image/jpeg,image/png,image/webp"
                  :on-change="onCreateCoverPicked"
                >
                  <el-button plain>📤 选择图片（可选，生成 NFO 时一并补图）</el-button>
                </el-upload>
                <div v-if="createCoverFile" class="translate-btn-row">
                  <span>{{ createCoverFile.name }}</span>
                  <el-button size="small" text type="danger" @click="createCoverFile = null">移除</el-button>
                </div>
                <p class="upload-hint">图片基础名与 NFO 文件名一致：原图作 thumb，横图自动裁竖版 poster</p>
              </div>
            </el-form-item>
          </el-form>
        </template>
        <template v-else>
          <el-input
            :model-value="createResult.content"
            type="textarea"
            :autosize="{ minRows: 12, maxRows: 24 }"
            readonly
          />
        </template>
      </div>
      <template #footer>
        <template v-if="createResult">
          <el-button @click="copyCreatedNfo">复制</el-button>
          <el-button @click="downloadCreatedNfo">下载</el-button>
          <el-button @click="createResult = null">继续创建</el-button>
          <el-button type="primary" @click="createDialog = false">关闭</el-button>
        </template>
        <template v-else>
          <el-button @click="createDialog = false">取消</el-button>
          <el-button type="primary" :loading="createLoading" @click="onCreateNfo()">
            {{ createMode === 'scrape' ? '刮削' : '生成 NFO' }}
          </el-button>
        </template>
      </template>
    </el-dialog>
    <!-- 创建 NFO 表单弹窗结束 -->
    <el-card shadow="never" header="👩 Gfriends 头像库同步" class="mt">
          <DirPicker v-model="gfriendsPath" placeholder="Gfriends 本地仓库目录" class="mb" />
          <el-button :disabled="isRunning('Gfriends 同步')" @click="run('Gfriends 同步', () => api.toolsGfriends(gfriendsPath))">
            同步
          </el-button>
        </el-card>
        <el-card shadow="never" header="🔎 查找缺失番号" class="mt">
          <el-button :disabled="isRunning('查找缺失番号')" @click="run('查找缺失番号', api.toolsMissingNumber)">
            开始查找
          </el-button>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" header="📚 演员库维护（actor_database.xlsx）">
          <div class="btn-grid">
            <el-button :disabled="isRunning('补全中文名')" @click="onActorDb('translate')">补全中文名</el-button>
            <el-button :disabled="isRunning('补全 LibreDMM 链接')" @click="onActorDb('link')">补全 LibreDMM 链接</el-button>
            <el-button :disabled="isRunning('minnano 补全')" @click="onActorDb('fill_minnano')">minnano 补全</el-button>
            <el-button :disabled="isRunning('JavDB 中文名')" @click="onActorDb('fill_zh_javdb', { offset: actorDbOffset, limit: actorDbLimit })">
              JavDB 中文名
            </el-button>
            <el-button :disabled="isRunning('剔除男演员')" @click="onActorDb('clean_male')">剔除男演员</el-button>
            <el-button :disabled="isRunning('校验 tmdbid 有效性')" @click="onActorDb('verify_tmdbid')">校验 tmdbid 有效性</el-button>
            <el-button :disabled="isRunning('检查用户库')" @click="onActorDb('check')">检查用户库</el-button>
            <el-button :disabled="isRunning('更新 nfo tmdbid')" @click="onActorDb('update_nfo_tmdbid', { nfo_dir: actorDbNfoDir })">
              更新 nfo tmdbid
            </el-button>
          </div>
          <el-divider style="margin: 12px 0" />
          <div class="btn-row wrap">
            <el-select v-model="aliasSource" style="width: 110px">
              <el-option label="tmdb" value="tmdb" />
              <el-option label="JavDB" value="javdb" />
              <el-option label="minnano" value="avwiki" />
            </el-select>
            <el-checkbox v-model="aliasAll" label="全量并入" />
            <el-input-number v-model="actorDbOffset" :min="0" placeholder="起始行" controls-position="right" style="width: 110px" />
            <el-input-number v-model="actorDbLimit" :min="0" placeholder="限量(0=不限)" controls-position="right" style="width: 130px" />
            <el-button :disabled="isRunning('补全别名')" @click="onActorDb('sync_aliases', { alias_source: aliasSource, overwrite: aliasAll, offset: actorDbOffset, limit: actorDbLimit })">
              补全别名
            </el-button>
          </div>
          <div class="btn-row mt">
            <DirPicker v-model="actorDbNfoDir" placeholder="nfo 目录（更新 nfo tmdbid 用）" class="grow" />
          </div>
        </el-card>

        <el-card shadow="never" header="👩 Emby 演员批量补全" class="mt">
          <p class="upload-hint">
            按 gfriends 头像库自动匹配并写入 Emby；需先在「软件设置」配置 Emby 地址 / API Key / 用户 ID，进度见日志页
          </p>
          <div class="btn-row">
            <el-button :disabled="isRunning('演员头像写入')" @click="run('演员头像写入', api.actorPhotoSync)">
              头像批量写入
            </el-button>
            <el-button :disabled="isRunning('演员信息写入')" @click="run('演员信息写入', api.actorInfoSync)">
              信息批量写入
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" header="🗄️ 刮削缓存管理" class="mt">
          <div v-if="cacheStats" class="cache-stats">
            <span>已完成 {{ cacheStats.done }}</span>
            <span>失败 {{ cacheStats.failed }}</span>
            <span>超限失败 {{ cacheStats.failed_exhausted }}</span>
            <span>总计 {{ cacheStats.total }}</span>
            <span>{{ cacheStats.db_path }}（{{ cacheStats.db_size_kb }} KB）</span>
          </div>
          <div class="btn-row mt">
            <el-button @click="refreshCache">刷新</el-button>
            <el-button @click="onExportCache">导出失败列表 CSV</el-button>
            <el-button @click="onCacheDeleteSelected">重置选中记录</el-button>
            <el-button type="danger" plain @click="onCacheClear">清空缓存</el-button>
          </div>
          <el-table
            :data="cacheFailed"
            size="small"
            height="220"
            class="mt"
            @selection-change="(rows: any[]) => (failedSelection = rows)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column prop="number" label="番号" width="140" />
            <el-table-column prop="fail_count" label="失败次数" width="80" />
            <el-table-column prop="error" label="最后错误" min-width="200" show-overflow-tooltip />
            <el-table-column prop="scraped_at" label="时间" width="150" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.tools-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tip .ml {
  margin: 0 4px;
}
.mb {
  margin-bottom: 10px;
}
.translate-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.stack-full {
  width: 100%;
}
.translate-btn-row {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}
.labeled-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.labeled-row .row-label {
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
  width: 62px;
}
.labeled-row .grow {
  flex: 1;
  min-width: 0;
}
.mt {
  margin-top: 12px;
}
.btn-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.btn-row.wrap {
  flex-wrap: wrap;
}
.btn-row .grow {
  flex: 1;
}
.btn-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.btn-grid .el-button {
  margin-left: 0;
}
.upload-hint {
  color: #909399;
  font-size: 12px;
  margin: 4px 0 0;
}
.translate-result {
  min-height: 200px;
}
.field-info {
  margin-top: 10px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}
.field-info .warn {
  color: var(--el-color-warning);
  margin-left: 8px;
}
.translate-log {
  margin: 10px 0 0;
  max-height: 140px;
  overflow: auto;
  background: #f5f7fa;
  color: #606266;
  font-size: 12px;
  border-radius: 6px;
  padding: 8px 10px;
  white-space: pre-wrap;
}
.result-pre {
  margin: 0;
  max-height: 55vh;
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.7;
  border-radius: 6px;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.empty {
  color: #909399;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}
.cache-stats {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #606266;
  flex-wrap: wrap;
}
</style>
