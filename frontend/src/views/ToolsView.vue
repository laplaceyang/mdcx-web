<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useScrapeStore } from '../stores/scrape'

const scrape = useScrapeStore()

// 单文件刮削
const singleFile = ref('')
const singleUrl = ref('')
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
          <el-input v-model="singleFile" placeholder="视频文件绝对路径" class="mb" />
          <el-input v-model="singleUrl" placeholder="番号网址（如 https://javdb.com/...）" class="mb" />
          <el-button type="primary" :disabled="scrape.running || scrape.stopping" @click="onSingleScrape">
            刮削
          </el-button>
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
          <el-input v-model="backfillNumbers" type="textarea" :rows="2" placeholder="番号列表（空格分隔）" class="mb" />
          <div class="btn-row">
            <el-checkbox v-model="backfillOverwrite" label="覆盖已有图片" />
            <el-checkbox v-model="backfillWatermark" label="加水印" />
            <el-button type="primary" :disabled="isRunning('封面补图')" @click="onCoverBackfill">开始补图</el-button>
          </div>
        </el-card>
        <el-card shadow="never" header="👩 Gfriends 头像库同步" class="mt">
          <el-input v-model="gfriendsPath" placeholder="Gfriends 本地仓库目录" class="mb" />
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
            <el-input v-model="actorDbNfoDir" placeholder="nfo 目录（更新 nfo tmdbid 用）" class="grow" />
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
.cache-stats {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #606266;
  flex-wrap: wrap;
}
</style>
