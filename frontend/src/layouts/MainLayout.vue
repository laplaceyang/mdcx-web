<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useScrapeStore } from '../stores/scrape'
import { useWsStore } from '../stores/ws'

const route = useRoute()
const ws = useWsStore()
const scrape = useScrapeStore()

const countsText = computed(
  () =>
    `成功 ${scrape.status.counts.succ} / 失败 ${scrape.status.counts.fail} / 已完成 ${scrape.status.counts.done} / 共 ${scrape.status.counts.total}`,
)

onMounted(() => {
  ws.connect()
  scrape.initWs()
  void scrape.refresh()
  void scrape.loadResults()
})
onUnmounted(() => {})
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="160px" class="side">
      <div class="brand">MDCx <span class="brand-sub">Web</span></div>
      <el-menu :default-active="route.path" router class="nav">
        <el-menu-item index="/scrape">🎬 软件界面</el-menu-item>
        <el-menu-item index="/log">📝 软件日志</el-menu-item>
        <el-menu-item index="/tools">🧰 软件工具</el-menu-item>
        <el-menu-item index="/actors">👩 演员管理</el-menu-item>
        <el-menu-item index="/nfo">🗂️ 信息管理</el-menu-item>
        <el-menu-item index="/settings">⚙️ 软件设置</el-menu-item>
        <el-menu-item index="/network">📡 检测网络</el-menu-item>
        <el-menu-item index="/about">ℹ️ 关于</el-menu-item>
      </el-menu>
      <div class="conn">
        <el-tag :type="ws.connected ? 'success' : 'danger'" size="small" effect="plain">
          {{ ws.connected ? '已连接' : '连接断开' }}
        </el-tag>
      </div>
    </el-aside>
    <el-container>
      <el-main class="main"><router-view /></el-main>
      <el-footer height="52px" class="global-bar">
        <span class="info" :title="scrape.scrapeInfo">{{ scrape.scrapeInfo || '就绪' }}</span>
        <el-progress
          :percentage="scrape.status.progress"
          :stroke-width="14"
          :status="scrape.running ? undefined : scrape.status.progress >= 100 ? 'success' : undefined"
          class="bar"
        />
        <span class="counts">{{ countsText }}</span>
        <el-tag v-if="scrape.stopping" type="warning" size="small">停止中…</el-tag>
      </el-footer>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-shell {
  height: 100%;
}
.side {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid #e4e7ed;
}
.brand {
  font-size: 20px;
  font-weight: 700;
  padding: 16px;
  text-align: center;
}
.brand-sub {
  color: var(--el-color-primary);
  font-size: 14px;
}
.nav {
  border-right: none;
  flex: 1;
}
.conn {
  padding: 12px;
  text-align: center;
}
.main {
  padding: 12px;
  overflow: auto;
}
.global-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  padding: 0 16px;
}
.info {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
  font-size: 13px;
}
.bar {
  width: 320px;
}
.counts {
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}
</style>
