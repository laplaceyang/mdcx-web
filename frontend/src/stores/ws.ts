import { ref } from 'vue'
import { defineStore } from 'pinia'

type Handler = (event: string, args: unknown[]) => void

export const useWsStore = defineStore('ws', () => {
  const connected = ref(false)
  const handlers = new Set<Handler>()
  let ws: WebSocket | null = null
  let retry = 0
  let manualClose = false

  function connect() {
    manualClose = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws`)
    ws.onopen = () => {
      connected.value = true
      retry = 0
    }
    ws.onclose = () => {
      connected.value = false
      if (manualClose) return
      // 断线重连：指数退避，最长 10s。服务端 /ws 会补发 replay 缓冲
      const delay = Math.min(1000 * 2 ** retry++, 10000)
      setTimeout(connect, delay)
    }
    ws.onmessage = (e) => {
      let msg: { type: string; event?: string; args?: unknown[] }
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      if (msg.type === 'event' && msg.event) {
        for (const h of handlers) h(msg.event, msg.args ?? [])
      }
    }
  }

  function on(h: Handler): () => void {
    handlers.add(h)
    return () => handlers.delete(h)
  }

  return { connected, connect, on }
})
