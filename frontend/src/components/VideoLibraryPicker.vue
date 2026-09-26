<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type EmbyLibrary } from '../api/client'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const libraries = ref<EmbyLibrary[]>([])
const loading = ref(false)
const fetched = ref(false)

function label(l: EmbyLibrary): string {
  const type = { movies: '电影', tvshows: '电视剧', boxsets: '合集' }[l.type] ?? l.type
  // 库名已表意（如「电影」「电视剧」）时不再追加类型后缀
  if (!type || l.name === type) return l.name
  return `${l.name}（${type}）`
}

async function fetchLibraries() {
  loading.value = true
  try {
    const r = await api.embyLibraries()
    libraries.value = r.libraries
    fetched.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 已保存过库 id 时拉一次列表用于显示库名；没配置过则等用户填好连接信息后手动拉取
  if (props.modelValue) await fetchLibraries()
})
</script>

<template>
  <div class="picker">
    <el-select
      :model-value="modelValue"
      placeholder="先拉取媒体库再选择"
      clearable
      style="width: 280px"
      :loading="loading"
      @update:model-value="emit('update:modelValue', $event ?? '')"
    >
      <el-option v-for="l in libraries" :key="l.id" :label="label(l)" :value="l.id" />
    </el-select>
    <el-button :loading="loading" @click="fetchLibraries">拉取媒体库</el-button>
    <span class="hint">{{ fetched ? `共 ${libraries.length} 个库` : '填好上方连接信息后点「拉取媒体库」' }}</span>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
</style>
