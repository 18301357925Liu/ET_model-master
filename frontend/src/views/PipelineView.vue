<template>
  <div class="view">
    <h2>一键更新 Pipeline</h2>
    <p class="desc">重新运行完整的任务级聚类、负荷映射、模型训练流程。</p>

    <div class="form-card">
      <h3>参数设置</h3>
      <div class="form-grid">
        <label>
          数据目录
          <input v-model="form.data_root" placeholder="uploads/1/data" />
        </label>
        <label>
          聚类数量 K
          <input v-model.number="form.k" type="number" min="2" max="20" />
        </label>
        <label>
          聚类算法
          <select v-model="form.algo">
            <option value="kmeans">K-Means</option>
            <option value="agglo">层次聚类</option>
            <option value="dbscan">DBSCAN</option>
          </select>
        </label>
        <label>
          负荷映射模式
          <select v-model="form.mapping_mode">
            <option value="auto">自动</option>
            <option value="manual">手动</option>
          </select>
        </label>
        <label>
          分类器算法
          <select v-model="form.classifier_algo">
            <option value="svm">SVM</option>
            <option value="xgboost">XGBoost</option>
          </select>
        </label>
      </div>
      <button class="btn-primary" @click="runPipeline" :disabled="running">
        {{ running ? '运行中...' : '开始更新' }}
      </button>
    </div>

    <div v-if="steps.length" class="result-card">
      <h3>执行步骤</h3>
      <div v-for="step in steps" :key="step.name" class="step-item" :class="step.ok ? 'ok' : 'err'">
        <span class="step-name">{{ stepLabels[step.name] || step.name }}</span>
        <span class="step-msg">{{ step.message }}</span>
        <span v-if="!step.ok" class="step-detail">{{ step.stderr }}</span>
      </div>
      <div v-if="allOk" class="success-msg">Pipeline 更新完成！</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { rebuildPipeline } from '@/api'

const form = ref({
  data_root: 'uploads/1/data',
  k: 6,
  algo: 'kmeans',
  mapping_mode: 'auto',
  classifier_algo: 'svm',
})
const running = ref(false)
const steps = ref([])

const stepLabels = {
  task_cluster: '任务级聚类',
  summarize_cluster_load: '生成负荷映射',
  train_classifier: '训练监督模型',
}

const allOk = computed(() => steps.value.length > 0 && steps.value.every(s => s.ok))

async function runPipeline() {
  running.value = true
  steps.value = []
  try {
    const res = await rebuildPipeline(form.value)
    steps.value = res.data.steps || []
  } catch (e) {
    if (e.response?.data?.detail?.steps) {
      steps.value = e.response.data.detail.steps
    } else {
      steps.value = [{ name: 'error', ok: false, message: e.message, stderr: '' }]
    }
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.view { max-width: 700px; }
h2 { margin-bottom: 8px; }
.desc { color: #666; margin-bottom: 20px; font-size: 14px; }
.form-card, .result-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
}
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }
label { font-size: 13px; color: #555; display: flex; flex-direction: column; gap: 4px; }
input, select {
  padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px;
}
.btn-primary {
  background: #4fc3f7; color: #fff; border: none; padding: 10px 20px;
  border-radius: 4px; cursor: pointer; font-size: 14px;
}
.btn-primary:hover { background: #29b6f6; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.step-item {
  padding: 10px 12px; border-radius: 4px; margin-bottom: 8px;
  border-left: 4px solid #ddd; background: #f9f9f9;
}
.step-item.ok { border-color: #4caf50; }
.step-item.err { border-color: #f44336; }
.step-name { font-weight: bold; display: block; }
.step-msg { font-size: 13px; color: #555; }
.step-detail { font-size: 12px; color: #999; display: block; margin-top: 4px; }
.success-msg { color: #4caf50; font-weight: bold; padding: 12px; text-align: center; }
</style>
