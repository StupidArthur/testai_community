export type SseEvent =
  | { type: 'queued'; ahead: number; total: number }
  | {
      type: 'progress'
      phase: string
      step: number
      total_steps: number
      message: string
    }
  | { type: 'done'; status: string; error?: string | null }

export function subscribeJob(
  jobId: string,
  onEvent: (event: SseEvent) => void,
): () => void {
  const token = localStorage.getItem('token')
  if (!token) {
    return () => {}
  }
  // SECURITY NOTE: EventSource API 不支持自定义 Authorization header，
  // 因此 token 通过 URL query string 传递。这会导致 token 出现在浏览器历史
  // 和服务器访问日志中。JWT token 有 60 分钟有效期，风险可控。
  // TODO: 未来可改为短期一次性 ticket 机制进一步降低风险。
  const url = `/translate/api/jobs/${encodeURIComponent(jobId)}/stream?token=${encodeURIComponent(token)}`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as SseEvent
      onEvent(data)
    } catch {
      // ignore parse errors
    }
  }

  es.onerror = () => {
    // EventSource will auto-reconnect; we don't stop here
  }

  return () => {
    es.close()
  }
}
