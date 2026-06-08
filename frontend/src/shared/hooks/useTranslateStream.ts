import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { SseEvent } from '../api/translate-sse'
import { subscribeJob } from '../api/translate-sse'
import type { JobView } from '../api/translate-jobs'

export function useTranslateStream(jobId: string | undefined) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!jobId) return

    const unsubscribe = subscribeJob(jobId, (event: SseEvent) => {
      queryClient.setQueryData<JobView>(['job', jobId], (old) => {
        if (!old) return old
        switch (event.type) {
          case 'progress':
            return {
              ...old,
              status: 'running',
              current_phase: event.phase,
              current_step: event.step,
              total_steps: event.total_steps,
              message: event.message,
            }
          case 'done':
            return {
              ...old,
              status: event.status as JobView['status'],
              error: event.error ?? null,
            }
          default:
            return old
        }
      })

      if (event.type === 'done') {
        queryClient.invalidateQueries({ queryKey: ['jobs'] })
      }
    })

    return unsubscribe
  }, [jobId, queryClient])
}
