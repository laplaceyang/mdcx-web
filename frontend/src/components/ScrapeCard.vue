<script setup lang="ts">
import { Film, Loading } from '@element-plus/icons-vue'

defineProps<{
  number: string
  title: string
  /** 标题未就绪时的回退文案（如文件名），以弱化样式显示 */
  titleFallback?: string
  actors?: string
  /** 已解析好的图片 URL；为空显示占位 */
  image?: string | null
  /** 图片占位文案（等待封面 / 暂无封面） */
  placeholder?: string
  /** 底部等宽字体行：在途=最新日志，成功/失败=文件路径 */
  footer?: string
  footerTooltip?: string
  /** 失败原因（红色提示行，失败卡片专用） */
  error?: string
  selected?: boolean
}>()

defineEmits<{ click: []; contextmenu: [event: MouseEvent] }>()
</script>

<template>
  <div
    class="card"
    :class="{ selected }"
    @click="$emit('click')"
    @contextmenu.prevent="$emit('contextmenu', $event)"
  >
    <div class="card-main">
      <div class="card-poster-box" @click.stop>
        <el-image
          class="card-poster"
          :src="image ?? undefined"
          :preview-src-list="image ? [image] : []"
          fit="cover"
          lazy
          preview-teleported
        >
          <template #error>
            <div class="img-pending">
              <el-icon :size="22"><Film /></el-icon>
              <span>{{ placeholder || '暂无封面' }}</span>
            </div>
          </template>
          <template #placeholder>
            <div class="img-pending"><el-icon :size="22" class="is-loading"><Loading /></el-icon></div>
          </template>
        </el-image>
      </div>
      <div class="card-info">
        <div class="card-number" :title="number">{{ number }}</div>
        <div class="card-title" :class="{ placeholder: !title }" :title="title || titleFallback">
          {{ title || titleFallback }}
        </div>
        <div v-if="actors" class="card-actor" :title="actors">{{ actors }}</div>
        <div class="card-meta"><slot name="meta" /></div>
      </div>
    </div>
    <div v-if="error" class="card-error" :title="error">{{ error }}</div>
    <div v-if="footer" class="card-footer" :title="footerTooltip || footer">{{ footer }}</div>
  </div>
</template>

<style scoped>
.card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  animation: card-in 0.25s ease;
}
.card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
}
@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.card-main {
  display: flex;
  gap: 10px;
  min-width: 0;
}
.card-poster-box {
  flex-shrink: 0;
}
.card-poster {
  display: block;
  width: 84px;
  height: 112px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}
.img-pending {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 112px;
  color: #c0c4cc;
  font-size: 12px;
}
.card-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-number {
  font-size: 15px;
  font-weight: 700;
  color: var(--el-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-title {
  font-size: 13px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}
.card-title.placeholder {
  color: #909399;
}
.card-actor {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 12px;
  color: #909399;
  min-height: 1em;
}
.card-error {
  font-size: 12px;
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  border-radius: 4px;
  padding: 6px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-footer {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 12px;
  color: #909399;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 6px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
