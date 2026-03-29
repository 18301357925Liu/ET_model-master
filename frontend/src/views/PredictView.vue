<template>
  <div class="view">
    <h2>单 Session 预测</h2>
    <p class="desc">选择一个 session 目录，预测其中所有任务的 cluster / 负荷等级 / 2D 坐标。</p>

    <div class="form-card">
      <label>
        Session 目录路径
        <input v-model="sessionDir" placeholder="data/20260124_140152" />
      </label>
      <button class="btn-primary" @click="predict" :disabled="loading">
        {{ loading ? '预测中...' : '开始预测' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div v-if="results.length" class="result-card">
      <h3>预测结果 ({{ results.length }} 个任务)</h3>
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>Task</th>
            <th>Cluster</th>
            <th>负荷等级</th>
            <th>坐标 (x, y)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in results" :key="i">
            <td>{{ r.session_id }}</td>
            <td>{{ r.task_id || '—' }}</td>
            <td>{{ r.predicted_cluster }}</td>
            <td>
              <span class="badge" :class="`level-${r.relative_load_level}`">
                {{ r.relative_load_label }}
              </span>
            </td>
            <td class="mono">
              ({{ r.coordinates_2d.x.toFixed(3) }}, {{ r.coordinates_2d.y.toFixed(3) }})
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { predictSession } from '@/api'

const sessionDir = ref('')
const loading = ref(false)
const error = ref('')
const results = ref([])

async function predict() {
  if (!sessionDir.value.trim()) {
    error.value = '请输入 session 目录路径'
    return
  }
  loading.value = true
  error.value = ''
  results.value = []
  try {
    const res = await predictSession({ session_dir: sessionDir.value })
    results.value = res.data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.view { max-width: 800px; }
h2 { margin-bottom: 8px; }
.desc { color: #666; margin-bottom: 20px; font-size: 14px; }
.form-card, .result-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
}
label { font-size: 13px; color: #555; display: flex; flex-direction: column; gap: 4px; }
input { padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin-bottom: 12px; width: 100%; }
.btn-primary {
  background: #4fc3f7; color: #fff; border: none; padding: 10px 20px;
  border-radius: 4px; cursor: pointer; font-size: 14px;
}
.btn-primary:hover { background: #29b6f6; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.error { color: #f44336; font-size: 13px; margin-top: 8px; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f5f5f5; font-weight: 600; }
.mono { font-family: monospace; font-size: 12px; color: #666; }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px;
  color: #fff; background: #9e9e9e;
}
.level-0 { background: #bdbdbd; }
.level-1 { background: #4caf50; }
.level-2 { background: #ff9800; }
.level-3 { background: #f44336; }
.level-4 { background: #9c27b0; }
</style>
