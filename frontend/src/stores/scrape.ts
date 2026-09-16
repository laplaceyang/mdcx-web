import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, type ResultItem, type ScrapeStatus } from '../api/client'
import { useWsStore } from './ws'

const MAX_LOG_LINES = 1000
// 页面刚打开时服务端会补发历史事件，只保留尾部这些行，避免整段回放刷屏
const REPLAY_TAIL_LINES = 300
const MAX_DETAIL_CHARS = 150000

export const useScrapeStore = defineStore('scrape', () => {
  const status = ref<ScrapeStatus>({
    state: 'idle',
    progress: 0,
    results: 0,
    counts: { succ: 0, fail: 0, done: 0, total: 0, skipped: 0, restored: 0, in_progress: 0 },
    elapsed: 0,
  })
  const results = ref<ResultItem[]>([])
  // 结果去重键：loadResults 快照与 WS 实时事件在页面加载/重连瞬间可能重叠
  const seenResultKeys = new Set<string>()
  const mainLogs = ref<string[]>([])
  const failedLogs = ref<string[]>([])
  const netLogs = ref<string[]>([])
  const detailLogText = ref('')
  const scrapeInfo = ref('')
  // set_label_file_path：桌面版"正在刮削： n/N xx% \n 文件路径"标签，刮削中页签展示
  const currentFileLabel = ref('')
  const running = computed(() => status.value.state === 'running')
  const stopping = computed(() => status.value.state === 'stopping')

  function push(list: string[], line: unknown, replaying = false) {
    list.push(String(line ?? ''))
    const cap = replaying ? Math.min(REPLAY_TAIL_LINES, MAX_LOG_LINES) : MAX_LOG_LINES
    if (list.length > cap) list.splice(0, list.length - cap)
  }

  async function refresh() {
    try {
      status.value = await api.scrapeStatus()
    } catch {
      /* 服务器未就绪时静默 */
    }
  }

  function resultKey(item: ResultItem): string {
    const path = String((item.show as any)?.file_info?.file_path ?? '')
    return `${item.status}|${item.real_number}|${path}`
  }

  function addResult(item: ResultItem): boolean {
    const key = resultKey(item)
    if (seenResultKeys.has(key)) return false
    seenResultKeys.add(key)
    results.value.push(item)
    return true
  }

  function resetResults(items: ResultItem[]) {
    seenResultKeys.clear()
    for (const item of items) seenResultKeys.add(resultKey(item))
    results.value = items
  }

  async function loadResults() {
    try {
      resetResults((await api.scrapeResults()).items)
    } catch {
      /* ignore */
    }
  }

  let detailTimer: number | undefined
  let statusTimer: number | undefined

  function initWs() {
    const ws = useWsStore()
    ws.on((event, args, replaying) => {
      switch (event) {
        case 'log_text':
          push(mainLogs.value, args[0], replaying)
          break
        case 'net_info':
          push(netLogs.value, args[0], replaying)
          break
        case 'logs_failed_settext':
        case 'logs_failed_show':
        case 'view_failed_list_settext':
          push(failedLogs.value, args[0], replaying)
          break
        case 'scrape_info':
          scrapeInfo.value = String(args[0] ?? '')
          break
        case 'set_label_file_path':
          currentFileLabel.value = String(args[0] ?? '')
          break
        case 'label_result': {
          // 桌面版统计标签「刮削中：n 成功：m 失败：k」，逐任务推送，比 5 秒轮询更实时
          const m = /刮削中：(\d+)\s+成功：(\d+)\s+失败：(\d+)/.exec(String(args[0] ?? ''))
          if (m) {
            status.value.counts.in_progress = Number(m[1])
            status.value.counts.succ = Number(m[2])
            status.value.counts.fail = Number(m[3])
          }
          break
        }
        case 'exec_set_processbar':
          status.value.progress = Number(args[0] ?? 0)
          break
        case 'exec_show_list_name':
          addResult({ status: String(args[0]), real_number: String(args[2] ?? ''), show: args[1] as ResultItem['show'] })
          break
        case 'change_buttons_status':
          status.value.state = 'running'
          break
        case 'reset_buttons_status':
          status.value.state = 'idle'
          void refresh()
          break
      }
    })
    // 断线重连丢事件时，结果/状态以服务端为准整体重拉（结果列表不做逐条补发）
    ws.onResync(() => {
      void refresh()
      void loadResults()
    })
    // 详情日志缓冲走轮询排空（signal.add_log 通道）
    detailTimer = window.setInterval(async () => {
      try {
        const d = await api.detailLog()
        if (d.text) detailLogText.value = (detailLogText.value + '\n' + d.text).slice(-MAX_DETAIL_CHARS)
      } catch {
        /* ignore */
      }
    }, 1000)
    // 运行中低频轮询状态：elapsed/done/total 仅由服务端维护，label_result 只带三个计数
    statusTimer = window.setInterval(() => {
      if (status.value.state === 'running') void refresh()
    }, 5000)
  }

  return {
    status,
    results,
    mainLogs,
    failedLogs,
    netLogs,
    detailLogText,
    scrapeInfo,
    currentFileLabel,
    running,
    stopping,
    refresh,
    loadResults,
    resetResults,
    initWs,
  }
})
