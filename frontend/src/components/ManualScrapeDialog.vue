<script setup lang="ts">
// 创建 NFO / 手动刮削 共享对话框。
// 手动刮削模式：落盘到 {目录}/{番号}/，NFO → 封面 → 移视频串行执行，
// 后两步失败不阻塞前一步结果。软件工具（单文件刮削）与刮削页失败卡片共用。
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DirPicker from './DirPicker.vue'
import { api, ApiError } from '../api/client'

const visible = ref(false)
const loading = ref(false)
const translating = ref<'' | 'title' | 'outline'>('')
const result = ref<{ path: string; content: string; covers?: { thumb: string; poster: string }; video?: string } | null>(
  null,
)
const coverFile = ref<File | null>(null)
const mode = ref<'create' | 'scrape'>('create')
const videoPath = ref('')
const form = ref({
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
const dir = ref('')
const filename = ref('')
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

// 文件名默认跟随番号，手动改过后不再跟随
function onNumberInput() {
  if (!filenameTouched.value) filename.value = form.value.number.trim()
}

// originaltitle/originalplot → title/plot：复用正常流程的按字段翻译；force=手动按钮时强制覆盖
async function translateField(field: 'title' | 'outline', force: boolean) {
  const src = field === 'title' ? form.value.originaltitle : form.value.originalplot
  if (!src.trim()) {
    if (force) ElMessage.warning(field === 'title' ? '请先填写原标题' : '请先填写原简介')
    return
  }
  if (translating.value === field) return
  if (!force && (field === 'title' ? titleTouched.value : plotTouched.value)) return // 手动改过目标字段则不覆盖
  translating.value = field
  try {
    const d = await api.translateTest('text', { text: src, field })
    const translated = (d.content ?? '').trim()
    if (field === 'title') {
      const n = form.value.number.trim()
      form.value.title = n && !translated.startsWith(n) ? `${n} ${translated}` : translated
      titleTouched.value = false
    } else {
      form.value.plot = translated
      plotTouched.value = false
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    translating.value = ''
  }
}

function splitList(text: string): string[] {
  return text
    .split(/[,，\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function onCoverPicked(uploadFile: { raw?: File }) {
  if (uploadFile.raw) coverFile.value = uploadFile.raw
}

async function open(opts: { mode?: 'create' | 'scrape'; videoPath?: string; number?: string } = {}) {
  mode.value = opts.mode ?? 'create'
  videoPath.value = opts.videoPath ?? ''
  form.value = {
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
  result.value = null
  coverFile.value = null
  visible.value = true
  if (mode.value === 'scrape' && videoPath.value) {
    // 番号默认值：按正常流程规则从文件名自动提取；提取不到回退调用方给的值，再不行留空手填
    try {
      const d = await api.extractNumber(videoPath.value)
      form.value.number = d.number || opts.number || ''
    } catch {
      form.value.number = opts.number || ''
    }
    if (form.value.number) onNumberInput()
  }
  defaultCreateDir().then((d) => {
    if (visible.value && !dir.value) dir.value = d
  })
}

async function submit(overwrite = false) {
  const f = form.value
  const scraping = mode.value === 'scrape'
  if (scraping && !f.number.trim()) {
    ElMessage.warning('请填写番号（用作文件夹和视频文件名）')
    return
  }
  if (!filename.value.trim() && !f.number.trim()) {
    ElMessage.warning('请填写番号或文件名')
    return
  }
  loading.value = true
  try {
    const subfolder = scraping ? f.number.trim() : ''
    const d = await api.nfoCreate({
      dir: dir.value,
      subfolder,
      filename: filename.value,
      overwrite,
      fields: {
        number: f.number.trim(),
        release: f.release,
        title: f.title.trim(),
        originaltitle: f.originaltitle.trim(),
        originalplot: f.originalplot.trim(),
        plot: f.plot.trim(),
        actors: splitList(f.actors),
        series: f.series.trim(),
        studio: f.studio.trim(),
        publisher: f.publisher.trim(),
        genres: splitList(f.genres),
        countrycode: f.countrycode.trim(),
      },
    })
    result.value = { path: d.path, content: d.content }
    // 补图：与 NFO 同目录、基础名同 NFO 文件名（后端与 NFO 命名共用同一清洗规则）
    if (coverFile.value) {
      try {
        const name = filename.value.trim() || f.number.trim()
        const c = await api.nfoCreateCover(name, dir.value, subfolder, coverFile.value)
        result.value = { ...result.value!, covers: { thumb: c.thumb, poster: c.poster } }
      } catch (e) {
        ElMessage.error(`NFO 已创建，但补图失败：${e instanceof Error ? e.message : String(e)}`)
      }
    }
    // 手动刮削：视频移入番号目录并改名为番号（保留原扩展名）
    if (scraping && videoPath.value) {
      try {
        const mv = await api.nfoMoveVideo(videoPath.value, dir.value, subfolder, f.number.trim(), overwrite)
        result.value = { ...result.value!, video: mv.path }
      } catch (e) {
        ElMessage.error(`NFO 已创建，但视频移动失败：${e instanceof Error ? e.message : String(e)}`)
      }
    }
    ElMessage.success(scraping ? `刮削完成：${d.path}` : `NFO 已创建：${d.path}`)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && !overwrite) {
      try {
        await ElMessageBox.confirm(`${e.message}，是否覆盖？`, '文件已存在', { type: 'warning' })
        await submit(true)
      } catch {
        /* 取消覆盖 */
      }
    } else {
      ElMessage.error(e instanceof Error ? e.message : String(e))
    }
  } finally {
    loading.value = false
  }
}

function copyResult() {
  if (!result.value) return
  navigator.clipboard
    .writeText(result.value.content)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}

function downloadResult() {
  if (!result.value) return
  const blob = new Blob([result.value.content], { type: 'text/xml;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = result.value.path.split('/').pop() || 'created.nfo'
  a.click()
  URL.revokeObjectURL(a.href)
}

defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" :title="mode === 'scrape' ? '手动刮削' : '创建 NFO'" width="720px" top="5vh" :close-on-click-modal="false">
    <div v-loading="loading">
      <el-alert
        v-if="result"
        type="success"
        :closable="false"
        class="mb"
        :title="`${mode === 'scrape' ? '已刮削' : '已创建'}：${result.path}`"
      >
        <div v-if="result.covers">封面图：{{ result.covers.thumb }}<br />{{ result.covers.poster }}</div>
        <div v-if="result.video">视频：{{ result.video }}</div>
      </el-alert>
      <template v-if="!result">
        <el-form label-width="70px">
          <el-row :gutter="10">
            <el-col :span="12">
              <el-form-item label="番号">
                <el-input v-model="form.number" placeholder="如 OFJE-536" @input="onNumberInput" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="发行日期">
                <el-input v-model="form.release" placeholder="YYYY-MM-DD，可留空" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="原标题">
            <el-input
              v-model="form.originaltitle"
              placeholder="填写后自动翻译，生成带番号的标题"
              @blur="translateField('title', false)"
            >
              <template #append>
                <el-button :loading="translating === 'title'" @click="translateField('title', true)"> 翻译 </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="标题">
            <el-input v-model="form.title" placeholder="留空时可由原标题翻译生成" @input="titleTouched = true" />
          </el-form-item>
          <el-form-item label="原简介">
            <div class="stack-full">
              <el-input
                v-model="form.originalplot"
                type="textarea"
                :rows="2"
                placeholder="填写后自动翻译，生成简介"
                @blur="translateField('outline', false)"
              />
              <div class="translate-btn-row">
                <el-button
                  size="small"
                  text
                  type="primary"
                  :loading="translating === 'outline'"
                  @click="translateField('outline', true)"
                >
                  翻译
                </el-button>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="简介">
            <el-input
              v-model="form.plot"
              type="textarea"
              :rows="3"
              placeholder="可选；留空时可由原简介翻译生成"
              @input="plotTouched = true"
            />
          </el-form-item>
          <el-divider content-position="left" style="margin: 6px 0 14px">详细信息（可选）</el-divider>
          <el-form-item label="演员">
            <el-input v-model="form.actors" type="textarea" :rows="2" placeholder="多个演员用换行或逗号分隔" />
          </el-form-item>
          <el-row :gutter="10">
            <el-col :span="8">
              <el-form-item label="系列">
                <el-input v-model="form.series" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="片商">
                <el-input v-model="form.studio" placeholder="写入 studio/maker" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="发行">
                <el-input v-model="form.publisher" placeholder="写入 publisher/label" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="10">
            <el-col :span="16">
              <el-form-item label="标签">
                <el-input v-model="form.genres" placeholder="多个标签用逗号分隔（写入 genre）" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="国家">
                <el-select v-model="form.countrycode" filterable allow-create default-first-option style="width: 100%">
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
              <DirPicker v-model="dir" placeholder="留空时保存到成功输出目录" />
              <p v-if="mode === 'scrape'" class="upload-hint">
                将在该目录下创建以番号命名的文件夹，NFO/封面/视频都放进去
              </p>
            </div>
          </el-form-item>
          <el-form-item label="文件名">
            <el-input v-model="filename" placeholder="默认使用番号，自动补 .nfo" @input="filenameTouched = true">
              <template #append>.nfo</template>
            </el-input>
          </el-form-item>
          <el-form-item label="封面图">
            <div class="stack-full">
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                accept="image/jpeg,image/png,image/webp"
                :on-change="onCoverPicked"
              >
                <el-button plain>📤 选择图片（可选，生成 NFO 时一并补图）</el-button>
              </el-upload>
              <div v-if="coverFile" class="translate-btn-row">
                <span>{{ coverFile.name }}</span>
                <el-button size="small" text type="danger" @click="coverFile = null">移除</el-button>
              </div>
              <p class="upload-hint">图片基础名与 NFO 文件名一致：原图作 thumb，横图自动裁竖版 poster</p>
            </div>
          </el-form-item>
        </el-form>
      </template>
      <template v-else>
        <el-input :model-value="result.content" type="textarea" :autosize="{ minRows: 12, maxRows: 24 }" readonly />
      </template>
    </div>
    <template #footer>
      <template v-if="result">
        <el-button @click="copyResult">复制</el-button>
        <el-button @click="downloadResult">下载</el-button>
        <el-button @click="result = null">继续创建</el-button>
        <el-button type="primary" @click="visible = false">关闭</el-button>
      </template>
      <template v-else>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submit()">
          {{ mode === 'scrape' ? '刮削' : '生成 NFO' }}
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style scoped>
.mb {
  margin-bottom: 10px;
}
.stack-full {
  width: 100%;
}
.translate-btn-row {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}
.upload-hint {
  color: #909399;
  font-size: 12px;
  margin: 4px 0 0;
}
</style>
