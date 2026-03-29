<template>
  <div class="view">
    <h2>AI 学习建议</h2>
    <p class="desc">基于当前认知负荷数据，由 Qwen 大模型生成个性化学习建议。</p>

    <div class="form-card">
      <label>
        Session 筛选（留空则使用全部数据）
        <input v-model="sessionFilter" placeholder="可选：按 session 名称过滤" />
      </label>
      <button class="btn-primary" @click="getAdvice" :disabled="streaming">
        {{ streaming ? '生成中...' : '获取建议' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div class="advice-card" v-if="advice || streaming">
      <h3>分析结果</h3>
      <div v-if="streaming && !advice" class="streaming-indicator">
        <span class="dot"></span> AI 正在思考中...
      </div>
      <div v-if="advice" class="markdown-body" v-html="renderedAdvice"></div>
    </div>

    <div v-if="!advice && !streaming" class="empty">
      点击「获取建议」开始分析。
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { getAIAdviceStream } from '@/api'

const sessionFilter = ref('')
const streaming = ref(false)
const advice = ref('')
const error = ref('')
const renderedAdvice = ref('')

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

function simpleMarkdown(text) {
  // Very basic markdown to HTML (no external deps)
  let html = escapeHtml(text)
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
  html = html.replace(/\n\n/g, '</p><p>')
  html = `<p>${html}</p>`
  return html
}

async function getAdvice() {
  streaming.value = true
  advice.value = ''
  renderedAdvice.value = ''
  error.value = ''

  try {
    const response = await getAIAdviceStream(sessionFilter.value)

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim()
          if (data === '[DONE]' || data.startsWith('[ERROR]') || data.startsWith('[TIMEOUT]') || data.startsWith('[HTTP ')) {
            streaming.value = false
            return
          }
          try {
            const obj = JSON.parse(data)
            const content = obj.choices?.[0]?.delta?.content
            if (content) {
              advice.value += content
              renderedAdvice.value = simpleMarkdown(advice.value)
            }
          } catch {
            // Skip unparseable chunks
          }
        }
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    streaming.value = false
  }
}
</script>

<style scoped>
.view { max-width: 800px; }
h2 { margin-bottom: 8px; }
.desc { color: #666; margin-bottom: 20px; font-size: 14px; }
.form-card, .advice-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
}
label { font-size: 13px; color: #555; display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
input { padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
.btn-primary {
  background: #4fc3f7; color: #fff; border: none; padding: 10px 20px;
  border-radius: 4px; cursor: pointer; font-size: 14px;
}
.btn-primary:hover { background: #29b6f6; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.error { color: #f44336; font-size: 13px; margin-top: 8px; }
.streaming-indicator { display: flex; align-items: center; gap: 8px; color: #999; padding: 8px 0; }
.dot {
  width: 8px; height: 8px; background: #4fc3f7; border-radius: 50%;
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.markdown-body { line-height: 1.7; color: #333; font-size: 14px; }
.markdown-body :deep(h2) { font-size: 18px; margin: 16px 0 8px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
.markdown-body :deep(h3) { font-size: 16px; margin: 14px 0 6px; }
.markdown-body :deep(h4) { font-size: 14px; margin: 12px 0 6px; }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(ul) { padding-left: 20px; margin: 8px 0; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(strong) { color: #1a1a2e; }
.empty { text-align: center; padding: 40px; color: #999; }
</style>
