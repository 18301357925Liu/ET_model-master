<template>
  <div class="view">
    <h2>实时监控</h2>
    <p class="desc">监控指定目录中的新 session，自动预测并记录。</p>

    <div class="form-card">
      <div class="flex">
        <label>
          监控目录（逗号分隔）
          <input v-model="watchDirs" placeholder="data, Cognitive/data/cognitive_study" />
        </label>
        <label>
          检测间隔（秒）
          <input v-model.number="interval" type="number" min="5" max="300" />
        </label>
        <div class="status-badge" :class="monitorStatus.running ? 'running' : 'stopped'">
          {{ monitorStatus.running ? '运行中' : '已停止' }}
        </div>
      </div>
      <div class="actions">
        <button class="btn-success" @click="startMonitor" :disabled="monitorStatus.running || starting">
          {{ starting ? '启动中...' : '启动监控' }}
        </button>
        <button class="btn-danger" @click="stopMonitor" :disabled="!monitorStatus.running || stopping">
          {{ stopping ? '停止中...' : '停止监控' }}
        </button>
        <button class="btn-outline" @click="loadStatus" :disabled="loading">刷新状态</button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-if="predictions.length" class="table-card">
      <h3>最近预测记录</h3>
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>Task</th>
            <th>Cluster</th>
            <th>负荷等级</th>
            <th>坐标</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(p, i) in predictions" :key="i">
            <td>{{ p.session_dir }}</td>
            <td>{{ p.task_id }}</td>
            <td>{{ p.predicted_cluster }}</td>
            <td>{{ p.relative_load_label }}</td>
            <td class="mono">
              ({{ p.coordinates_2d[0]?.toFixed(3) }}, {{ p.coordinates_2d[1]?.toFixed(3) }})
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getMonitorStatus, startMonitor as apiStartMonitor, stopMonitor as apiStopMonitor, getRealtimePredictions } from '@/api'

const monitorStatus = ref({ running: false, log_path: null })
const predictions = ref([])
const loading = ref(false)
const starting = ref(false)
const stopping = ref(false)
const error = ref('')
const watchDirs = ref('data, Cognitive/data/cognitive_study')
const interval = ref(10)

async function loadStatus() {
  loading.value = true
  error.value = ''
  try {
    const [statusRes, predRes] = await Promise.all([
      getMonitorStatus(),
      getRealtimePredictions(50),
    ])
    monitorStatus.value = statusRes.data
    predictions.value = predRes.data.records || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function startMonitor() {
  starting.value = true
  error.value = ''
  try {
    await apiStartMonitor({
      watch_dirs: watchDirs.value.split(',').map(d => d.trim()).filter(Boolean),
      interval: interval.value,
    })
    await loadStatus()
  } catch (e) {
    error.value = e.message
  } finally {
    starting.value = false
  }
}

async function stopMonitor() {
  stopping.value = true
  error.value = ''
  try {
    await apiStopMonitor()
    await loadStatus()
  } catch (e) {
    error.value = e.message
  } finally {
    stopping.value = false
  }
}

onMounted(loadStatus)
</script>

<style scoped>
.view { max-width: 900px; }
h2 { margin-bottom: 8px; }
.desc { color: #666; margin-bottom: 20px; font-size: 14px; }
.form-card, .table-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
}
.flex { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
label { font-size: 13px; color: #555; display: flex; flex-direction: column; gap: 4px; }
input { padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
.actions { display: flex; gap: 10px; margin-top: 16px; align-items: center; }
.btn-success, .btn-danger, .btn-outline {
  border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px;
}
.btn-success { background: #4caf50; color: #fff; }
.btn-danger { background: #f44336; color: #fff; }
.btn-outline { background: #fff; border: 1px solid #4fc3f7; color: #4fc3f7; }
.btn-success:disabled, .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.status-badge {
  padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: bold;
}
.status-badge.running { background: #e8f5e9; color: #4caf50; }
.status-badge.stopped { background: #f5f5f5; color: #999; }
.error { color: #f44336; font-size: 13px; margin-top: 8px; }
.loading { text-align: center; padding: 20px; color: #999; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f5f5f5; font-weight: 600; }
.mono { font-family: monospace; font-size: 12px; color: #666; }
</style>
