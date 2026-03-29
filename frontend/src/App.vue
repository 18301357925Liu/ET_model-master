<template>
  <div class="app-container">
    <nav class="sidebar">
      <div class="logo">ET_model</div>
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: $route.path === item.path }"
      >
        {{ item.label }}
      </router-link>
      <div class="sidebar-footer">
        <span class="version">v1.0.0</span>
      </div>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
const navItems = [
  { path: '/pipeline', label: '一键更新' },
  { path: '/predict', label: '单Session预测' },
  { path: '/tasks', label: '任务级浏览' },
  { path: '/realtime', label: '实时监控' },
  { path: '/ai-advice', label: 'AI学习建议' },
  { path: '/logs', label: '更新日志' },
]
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #f5f7fa;
  color: #333;
}

.app-container {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 200px;
  background: #1a1a2e;
  color: #fff;
  padding: 20px 0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.logo {
  font-size: 18px;
  font-weight: bold;
  padding: 0 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  margin-bottom: 10px;
}

.nav-item {
  padding: 12px 20px;
  color: rgba(255,255,255,0.7);
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s;
}

.nav-item:hover { background: rgba(255,255,255,0.05); color: #fff; }
.nav-item.active { background: rgba(255,255,255,0.1); color: #fff; border-left: 3px solid #4fc3f7; }

.sidebar-footer {
  margin-top: auto;
  padding: 20px;
  border-top: 1px solid rgba(255,255,255,0.1);
  font-size: 12px;
  color: rgba(255,255,255,0.4);
}

.content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>
