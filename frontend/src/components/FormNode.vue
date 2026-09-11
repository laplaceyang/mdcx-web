<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * Schema 驱动的递归表单节点：
 * boolean→switch、integer→number、enum→select、string[]→可创建多选、
 * string→input/textarea、object→递归分组、其余→JSON 文本框兜底。
 * object/array 直接修改传入的响应式 model，标量通过 v-model 上抛。
 */
const props = defineProps<{
  node: Record<string, any>
  modelValue?: any
  defs: Record<string, any>
  label?: string
  model?: Record<string, any>
  fieldKey?: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: any): void }>()

defineOptions({ name: 'FormNode' })

function resolve(node: any, depth = 0): any {
  if (!node || depth > 6) return { type: 'string' }
  if (node.$ref) {
    const name = node.$ref.split('/').pop()
    return resolve(props.defs[name], depth + 1)
  }
  if (node.anyOf) {
    const nonNull = node.anyOf.find((s: any) => s.type !== 'null' && !s.$ref?.includes('null'))
    if (nonNull) return { ...resolve(nonNull, depth + 1), nullable: node.anyOf.some((s: any) => s.type === 'null') }
  }
  if (node.type === 'array' && node.items) {
    return { ...node, items: resolve(node.items, depth + 1) }
  }
  return node
}

const resolved = computed(() => resolve(props.node))

const kind = computed(() => {
  const r = resolved.value
  if (r.type === 'boolean') return 'switch'
  if (r.type === 'integer' || r.type === 'number') return 'number'
  if (r.enum) return 'select'
  if (r.type === 'array') return r.items?.type === 'string' ? 'tags' : 'json'
  if (r.type === 'object') return 'object'
  if (r.type === 'string') return (r.maxLength ?? 0) > 160 || r.format === 'uri' ? 'textarea' : 'input'
  return 'json'
})

const enumOptions = computed(() => (resolved.value.enum ?? []).map((v: any) => String(v)))
const textValue = computed(() => (props.modelValue === undefined || props.modelValue === null ? '' : String(props.modelValue)))

const jsonText = ref('')
const jsonError = ref(false)
watchJson()

function watchJson() {
  try {
    jsonText.value = JSON.stringify(props.modelValue ?? null, null, 2)
    jsonError.value = false
  } catch {
    jsonText.value = ''
  }
}

function onJsonInput(value: string) {
  jsonText.value = value
  try {
    const parsed = JSON.parse(value)
    jsonError.value = false
    emit('update:modelValue', parsed)
  } catch {
    jsonError.value = true
  }
}

function update(value: any) {
  emit('update:modelValue', value)
}

function updateField(key: string, value: any) {
  emit('update:modelValue', { ...(props.modelValue ?? {}), [key]: value })
}
</script>

<template>
  <!-- 标量控件 -->
  <template v-if="kind === 'switch'">
    <el-switch :model-value="!!modelValue" @update:model-value="update" />
  </template>
  <template v-else-if="kind === 'number'">
    <el-input-number
      :model-value="Number(modelValue ?? 0)"
      :step="resolved.type === 'integer' ? 1 : 0.1"
      :value-on-error="0"
      controls-position="right"
      class="w-200"
      @update:model-value="update"
    />
  </template>
  <template v-else-if="kind === 'select'">
    <el-select
      :model-value="modelValue === null || modelValue === undefined ? '' : String(modelValue)"
      class="w-260"
      allow-create
      filterable
      @update:model-value="update"
    >
      <el-option v-if="resolved.nullable" label="（无）" value="" />
      <el-option v-for="v in enumOptions" :key="v" :label="v" :value="v" />
    </el-select>
  </template>
  <template v-else-if="kind === 'tags'">
    <el-select
      :model-value="(modelValue as string[]) ?? []"
      class="w-full"
      multiple
      filterable
      allow-create
      default-first-option
      :reserve-keyword="false"
      :placeholder="resolved.description || '输入后回车添加'"
      @update:model-value="update"
    >
      <el-option v-for="v in (modelValue as string[]) ?? []" :key="v" :label="v" :value="v" />
    </el-select>
  </template>
  <template v-else-if="kind === 'textarea'">
    <el-input
      type="textarea"
      :rows="3"
      :model-value="textValue"
      @update:model-value="update"
    />
  </template>
  <template v-else-if="kind === 'json'">
    <el-input type="textarea" :rows="4" :model-value="jsonText" @update:model-value="onJsonInput" />
    <div v-if="jsonError" class="json-err">JSON 格式错误，不会保存</div>
  </template>
  <template v-else-if="kind === 'object'">
    <div class="obj-group">
      <div v-for="(child, key) in resolved.properties ?? {}" :key="key" class="obj-field">
        <div class="obj-label">{{ child.title || key }}</div>
        <FormNode
          :node="child"
          :defs="defs"
          :model-value="(modelValue ?? {})[key]"
          @update:model-value="updateField(String(key), $event)"
        />
      </div>
    </div>
  </template>
  <template v-else>
    <el-input :model-value="textValue" class="w-360" @update:model-value="update" />
  </template>
</template>

<style scoped>
.w-200 {
  width: 200px;
}
.w-260 {
  width: 260px;
}
.w-360 {
  width: 360px;
}
.w-full {
  width: 100%;
}
.json-err {
  color: var(--el-color-danger);
  font-size: 12px;
}
.obj-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0 8px 12px;
  border-left: 2px solid var(--el-border-color);
}
.obj-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.obj-label {
  font-size: 13px;
  color: #606266;
}
</style>
