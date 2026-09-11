<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const version = ref<{ version_name: string; local_version: number; repo: string } | null>(null)
const info = ref<Record<string, any> | null>(null)
const checking = ref(false)
const updateState = ref<{ latest: number | null; has_new: boolean } | null>(null)

onMounted(async () => {
  try {
    version.value = await api.version()
    info.value = await api.info()
  } catch {
    /* ignore */
  }
})

async function onCheckUpdate() {
  checking.value = true
  try {
    const result = await api.checkUpdate()
    updateState.value = result
    if (result.has_new) {
      ElMessage.success(`有新版本！（${result.latest}）`)
    } else {
      ElMessage.info('当前已是最新版本')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <div class="about-view">
    <el-card shadow="never">
      <h2>MDCx <span class="sub">Web 版</span></h2>
      <p class="desc">
        从 36 个网站刮削视频元数据、生成 NFO、整理媒体库（Emby / Jellyfin / Kodi）。
        本版本将桌面 GUI 替换为 Web 界面，核心刮削引擎与桌面版完全一致。
      </p>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="当前版本">{{ version?.version_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="版本号">{{ version?.local_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="运行系统">{{ info?.system || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Python">{{ info?.python || '-' }}</el-descriptions-item>
        <el-descriptions-item label="配置文件" :span="2">{{ info?.config_path || '-' }}</el-descriptions-item>
        <el-descriptions-item label="数据目录" :span="2">{{ info?.data_folder || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div class="btns">
        <el-button type="primary" :loading="checking" @click="onCheckUpdate">检查更新</el-button>
        <el-button v-if="version?.repo" tag="a" :href="`https://github.com/${version.repo}`" target="_blank">
          GitHub 仓库
        </el-button>
        <el-tag v-if="updateState?.has_new" type="danger" class="ml">
          最新版本：{{ updateState?.latest }}，请及时更新！
        </el-tag>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.about-view {
  max-width: 860px;
}
.sub {
  color: var(--el-color-primary);
  font-size: 15px;
}
.desc {
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
}
.btns {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ml {
  margin-left: 8px;
}
</style>
