<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'

/**
 * 字段级站点优先级编辑器（桌面版 site_priority_dialog / field_priority 的 web 版）。
 * variant:
 *  - 'field'   → 字段配置 field_configs: dict[field, {site_prority, language, translate, skip}]
 *  - 'priority'→ 按类型字段优先级 type_field_configs: dict[type, dict[field, {site_prority, skip}]]
 */
const props = defineProps<{
  modelValue: Record<string, any>
  variant: 'field' | 'priority'
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: Record<string, any>): void }>()

// 可配置字段（与桌面 FIELD_PRIORITY_FIELDS 一致）
const FIELDS = [
  'title',
  'originaltitle',
  'outline',
  'originalplot',
  'actors',
  'all_actors',
  'thumb',
  'poster',
  'extrafanart',
  'trailer',
  'tags',
  'release',
  'runtime',
  'score',
  'directors',
  'series',
  'studio',
  'publisher',
  'wanted',
]
const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  originaltitle: '原始标题',
  outline: '简介',
  originalplot: '原始剧情',
  actors: '演员',
  all_actors: '全部演员',
  thumb: '缩略图',
  poster: '海报',
  extrafanart: '额外剧照',
  trailer: '预告片',
  tags: '标签',
  release: '发行日期',
  runtime: '片长',
  score: '评分',
  directors: '导演',
  series: '系列',
  studio: '制作商',
  publisher: '发行商',
  wanted: '想要人数',
}
const TYPES = [
  { value: 'youma', label: '有码' },
  { value: 'wuma', label: '无码' },
  { value: 'suren', label: '素人' },
  { value: 'fc2', label: 'FC2' },
  { value: 'oumei', label: '欧美' },
  { value: 'guochan', label: '国产' },
]
const LANGUAGES = [
  { value: 'undefined', label: '未指定' },
  { value: 'unknown', label: '未知' },
  { value: 'zh_cn', label: '简体中文' },
  { value: 'zh_tw', label: '繁体中文' },
  { value: 'jp', label: '日文' },
  { value: 'en', label: '英文' },
]

const sites = ref<string[]>([])
const selectedType = ref(TYPES[0].value)
const selectedField = ref(FIELDS[0])

onMounted(async () => {
  try {
    sites.value = (await api.configSites()).sites.map((s) => s.site)
  } catch {
    /* ignore */
  }
})

function entryDefaults(): Record<string, any> {
  return props.variant === 'field'
    ? { site_prority: [], language: 'undefined', translate: true, skip: false }
    : { site_prority: [], skip: false }
}

/** 读取当前编辑条目（不存在时返回默认值副本，不产生副作用）。 */
const current = computed<Record<string, any>>(() => {
  const root = props.modelValue ?? {}
  if (props.variant === 'priority') {
    const byType = (root[selectedType.value] ?? {}) as Record<string, any>
    return byType[selectedField.value] ?? entryDefaults()
  }
  return root[selectedField.value] ?? entryDefaults()
})

/** 确保当前条目存在并返回其引用（仅在用户主动修改时调用）。 */
function ensureEntry(): Record<string, any> {
  const root = props.modelValue ?? {}
  if (props.variant === 'priority') {
    root[selectedType.value] ??= {}
    root[selectedType.value][selectedField.value] ??= entryDefaults()
    return root[selectedType.value][selectedField.value]
  }
  root[selectedField.value] ??= entryDefaults()
  return root[selectedField.value]
}

function update(patch: Record<string, any>) {
  const entryObj = ensureEntry()
  Object.assign(entryObj, patch)
  // 浅拷贝触发外层响应式更新（嵌套引用原位修改已生效）
  emit('update:modelValue', { ...props.modelValue })
}
</script>

<template>
  <div class="fpe">
    <div class="selectors">
      <el-select
        v-if="variant === 'priority'"
        v-model="selectedType"
        class="type-select"
      >
        <el-option v-for="t in TYPES" :key="t.value" :label="`按类型：${t.label}`" :value="t.value" />
      </el-select>
      <el-select v-model="selectedField" filterable class="field-select">
        <el-option v-for="f in FIELDS" :key="f" :label="FIELD_LABELS[f] || f" :value="f" />
      </el-select>
    </div>

    <div class="editor">
      <div class="block">
        <div class="block-title">来源网站优先级（按选择顺序，先选的优先）</div>
        <el-select
          :model-value="(current?.site_prority as string[]) ?? []"
          class="w-full"
          multiple
          filterable
          :reserve-keyword="false"
          placeholder="依次点击站点设定优先级"
          @update:model-value="update({ site_prority: $event })"
        >
          <el-option v-for="s in sites" :key="s" :label="s" :value="s" />
        </el-select>
        <div v-if="(current?.site_prority as string[])?.length" class="order">
          <el-tag v-for="(s, i) in (current?.site_prority as string[])" :key="s" size="small" class="order-tag">
            {{ Number(i) + 1 }}. {{ s }}
          </el-tag>
        </div>
        <p class="hint">不选 = 使用全局站点优先级；留空的字段按“跳过此字段”开关处理</p>
      </div>

      <div v-if="variant === 'field'" class="block">
        <div class="block-title">语言偏好</div>
        <el-select :model-value="current?.language ?? 'undefined'" @update:model-value="update({ language: $event })">
          <el-option v-for="l in LANGUAGES" :key="l.value" :label="l.label" :value="l.value" />
        </el-select>
        <div class="switch-line">
          <el-switch
            :model-value="current?.translate ?? true"
            active-text="翻译此字段"
            @update:model-value="update({ translate: $event })"
          />
        </div>
      </div>

      <div class="block">
        <div class="block-title">抓取开关</div>
        <el-switch
          :model-value="!(current?.skip ?? false)"
          active-text="抓取此字段"
          inactive-text="跳过此字段"
          @update:model-value="update({ skip: !$event })"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.selectors {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.type-select {
  width: 180px;
}
.field-select {
  flex: 1;
}
.editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.block-title {
  font-size: 13px;
  color: #303133;
  margin-bottom: 6px;
  font-weight: 600;
}
.order {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.order-tag {
  font-family: ui-monospace, Menlo, monospace;
}
.switch-line {
  margin-top: 10px;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-top: 6px;
}
.w-full {
  width: 100%;
}
</style>
