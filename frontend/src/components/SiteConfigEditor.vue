<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'

/** 网站配置编辑器：每站自定义网址（留空 = 使用默认域名）。 */
const props = defineProps<{ modelValue: Record<string, string> }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: Record<string, string>): void }>()

const sites = ref<{ site: string; url: string }[]>([])
const keyword = ref('')

onMounted(async () => {
  try {
    sites.value = (await api.configSites()).sites
  } catch {
    /* ignore */
  }
})

const rows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return sites.value
    .filter((s) => !kw || s.site.toLowerCase().includes(kw) || s.url.toLowerCase().includes(kw))
    .map((s) => ({ site: s.site, defaultUrl: s.url, custom: String(props.modelValue?.[s.site] ?? '') }))
})

function onInput(site: string, value: string) {
  const next = { ...(props.modelValue ?? {}) }
  const v = value.trim()
  if (v) next[site] = v
  else delete next[site]
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="site-config">
    <el-input v-model="keyword" placeholder="过滤站点" clearable size="small" class="filter" />
    <el-table :data="rows" size="small" height="420" border>
      <el-table-column prop="site" label="站点" width="160" />
      <el-table-column label="默认网址" min-width="220">
        <template #default="{ row }">
          <span class="default-url">{{ row.defaultUrl }}</span>
        </template>
      </el-table-column>
      <el-table-column label="自定义网址（留空用默认）" min-width="260">
        <template #default="{ row }">
          <el-input
            size="small"
            :model-value="row.custom"
            :placeholder="row.defaultUrl"
            @update:model-value="onInput(row.site, $event)"
          />
        </template>
      </el-table-column>
    </el-table>
    <p class="hint">共 {{ rows.length }} 个站点；修改后需点击右上角「保存设置」</p>
  </div>
</template>

<style scoped>
.filter {
  width: 240px;
  margin-bottom: 8px;
}
.default-url {
  color: #909399;
  font-size: 12px;
  word-break: break-all;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-top: 6px;
}
</style>
