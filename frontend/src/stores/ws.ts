import { ref } from 'vue'
import { defineStore } from 'pinia'

type Handler = (event: string, args: unknown[]) => void

export const useWsStore = defineStore('ws', () => {
  const connected = ref(false)
  const handlers = new Set<Handler>()
  const resyncHandlers = new Set<() => void>()
  let ws: WebSocket | null = null
  let retry = 0
  let manualClose = false
  // 已处理的最大事件 seq：重连时带给服务端做增量补发；逐条去重防重叠
  let lastSeq = 0
  let gapDetected = false

  function connect() {
    manualClose = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws?after=${lastSeq}`)
    ws.onopen = () => {
      connected.value = true
      retry = 0
    }
    ws.onclose = () => {
      connected.value = false
      if (manualClose) return
      // 断线重连：指数退避，最长 10s。服务端按 lastSeq 增量补发日志事件
      const delay = Math.min(1000 * 2 ** retry++, 10000)
      setTimeout(connect, delay)
    }
    ws.onmessage = (e) => {
      let msg: { type: string; seq?: number; event?: string; args?: unknown[] }
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      if (msg.type === 'synced') {
        // 补发结束：若期间检测到 seq 跳变（缓冲溢出丢事件），让订阅方整体重拉
        if (gapDetected) {
          gapDetected = false
          for (const h of resyncHandlers) h()
        }
        return
      }
      if (msg.type !== 'event' || !msg.event) return
      const seq = typeof msg.seq === 'number' ? msg.seq : null
      if (seq !== null) {
        if (seq <= lastSeq) return // 重连补发与实时推送在注册瞬间可能重叠，按 seq 去重
        if (seq > lastSeq + 1) gapDetected = true
        lastSeq = seq
      }
      for (const h of handlers) h(msg.event, msg.args ?? [])
    }
  }

  function on(h: Handler): () => void {
    handlers.add(h)
    return () => handlers.delete(h)
  }

  function onResync(h: () => void): () => void {
    resyncHandlers.add(h)
    return () => resyncHandlers.delete(h)
  }

  return { connected, connect, on, onResync }
})
