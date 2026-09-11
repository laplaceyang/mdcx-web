<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <el-card>
    <el-empty :description="description || `「${title}」页面在 Phase 3（全功能对齐）中实现，敬请期待`">
      <template #image-size></template>
    </el-empty>
  </el-card>
</template>
