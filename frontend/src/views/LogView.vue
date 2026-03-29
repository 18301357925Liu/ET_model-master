<template>
  <div class="view">
    <h2>更新日志</h2>
    <p class="desc">查看 Pipeline 更新与系统操作历史记录。</p>

    <div class="actions">
      <button class="btn-outline" @click="load" :disabled="loading">刷新</button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="!entries.length && !loading" class="empty">
      暂无日志记录。
    </div>

    <div v-if="entries.length" class="log-card">
      <div v-for="(entry, i) in entries" :key="i" class="log-item" :class="entry.status">
        <div class="log-header">
          <span class="log-time">{{ entry.timestamp }}</span>
          <span class="log-action">{{ entry.action }}</span>
          <span class="log-status-badge" :class="entry.status">{{ entry.status }}</span>
        </div>
        <p class="log-msg">{{ entry.message }}</p>
        <p v-if="entry.extra" class="log-extra">{{ JSON.stringify(entry.extra) }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getLogs } from '@/api'

const entries = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getLogs(50)
    entries.value = res.data.entries || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.view { max-width: 800px; }
h2 { margin-bottom: 8px; }
.desc { color: #666; margin-bottom: 16px; font-size: 14px; }
.actions { margin-bottom: 16px; }
.btn-outline { background: #fff; border: 1px solid #4fc3f7; color: #4fc3f7; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }
.log-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.log-item {
  padding: 12px 0; border-bottom: 1px solid #eee;
  border-left: 3px solid transparent; padding-left: 12px;
}
.log-item:last-child { border-bottom: none; }
.log-item.success { border-color: #4caf50; }
.log-item.error { border-color: #f44336; }
.log-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.log-time { font-size: 12px; color: #999; font-family: monospace; }
.log-action { font-size: 13px; font-weight: bold; color: #333; }
.log-status-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: bold;
}
.log-status-badge.success { background: #e8f5e9; color: #4caf50; }
.log-status-badge.error { background: #ffebee; color: #f44336; }
.log-msg { font-size: 13px; color: #555; }
.log-extra { font-size: 11px; color: #999; font-family: monospace; margin-top: 4px; }
.loading { text-align: center; padding: 20px; color: #999; }
.error { color: #f44336; font-size: 13px; margin-bottom: 12px; }
.empty { text-align: center; padding: 40px; color: #999; }
</style>
