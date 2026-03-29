<template>
  <div class="view">
    <h2>任务级浏览</h2>
    <p class="desc">浏览离线任务聚类结果与认知负荷等级。</p>

    <div class="form-card">
      <div class="flex">
        <label>
          按 Session 筛选
          <select v-model="session" @change="page = 1; load()">
            <option value="">全部</option>
            <option v-for="s in sessions" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn-outline" @click="load()" :disabled="loading">刷新</button>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="!records.length && !loading" class="empty">
      暂无数据，请先运行 Pipeline。
    </div>

    <div v-if="records.length" class="table-card">
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>Task</th>
            <th>Cluster</th>
            <th>负荷等级</th>
            <th>标签</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in records" :key="i">
            <td>{{ r.session }}</td>
            <td>{{ r.task_id }}</td>
            <td>{{ r.cluster }}</td>
            <td>{{ r.level || '—' }}</td>
            <td>{{ r.label || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination" v-if="totalPages > 1">
      <button @click="page--; load()" :disabled="page <= 1">上一页</button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button @click="page++; load()" :disabled="page >= totalPages">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { getTaskRecords } from '@/api'

const loading = ref(false)
const error = ref('')
const records = ref([])
const session = ref('')
const sessions = ref([])
const page = ref(1)
const limit = 20
const totalPages = ref(1)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getTaskRecords({ session: session.value || undefined, skip: (page.value - 1) * limit, limit })
    records.value = res.data.records || []
    sessions.value = [...new Set(records.value.map(r => r.session))].sort()
    totalPages.value = Math.max(1, Math.ceil(records.value.length / limit))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch([session, page], load)
onMounted(load)
</script>

<style scoped>
.view { max-width: 900px; }
h2 { margin-bottom: 8px; }
.desc { color: #666; margin-bottom: 20px; font-size: 14px; }
.form-card, .table-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
}
.flex { display: flex; align-items: center; gap: 12px; }
select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f5f5f5; font-weight: 600; }
.loading { text-align: center; padding: 20px; color: #999; }
.error { color: #f44336; font-size: 13px; }
.empty { text-align: center; padding: 40px; color: #999; }
.pagination { display: flex; align-items: center; gap: 12px; justify-content: center; margin-top: 16px; }
button { padding: 6px 14px; border: 1px solid #ddd; background: #fff; border-radius: 4px; cursor: pointer; font-size: 13px; }
button:hover { background: #f5f5f5; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-outline { background: #fff; border: 1px solid #4fc3f7; color: #4fc3f7; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
</style>
