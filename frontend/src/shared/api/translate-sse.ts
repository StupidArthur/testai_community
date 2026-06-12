import { fetchTicket } from './translate-client'

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
  let es: EventSource | null = null
  let stopped = false

  async function connect() {
    if (stopped) return
    const ticket = await fetchTicket()
    if (stopped) return
    const url = `/api/translate/jobs/${encodeURIComponent(jobId)}/stream?ticket=${encodeURIComponent(ticket)}`
    es = new EventSource(url)

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as SseEvent
        onEvent(data)
        if (data.type === 'done') {
          stopped = true
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      if (es) {
        es.close()
        es = null
      }
      if (!stopped) {
        setTimeout(() => connect(), 1000)
      }
    }
  }

  connect()

  return () => {
    stopped = true
    if (es) {
      es.close()
      es = null
    }
  }
}
