import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/pipeline' },
  { path: '/pipeline', component: () => import('../views/PipelineView.vue'), name: 'pipeline', meta: { title: '一键更新' } },
  { path: '/predict', component: () => import('../views/PredictView.vue'), name: 'predict', meta: { title: '单Session预测' } },
  { path: '/tasks', component: () => import('../views/TaskBrowseView.vue'), name: 'tasks', meta: { title: '任务级浏览' } },
  { path: '/realtime', component: () => import('../views/RealtimeView.vue'), name: 'realtime', meta: { title: '实时监控' } },
  { path: '/ai-advice', component: () => import('../views/AIAdviceView.vue'), name: 'ai-advice', meta: { title: 'AI学习建议' } },
  { path: '/logs', component: () => import('../views/LogView.vue'), name: 'logs', meta: { title: '更新日志' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  document.title = `${to.meta.title || 'ET_model'} - ET认知负荷系统`
})

export default router
