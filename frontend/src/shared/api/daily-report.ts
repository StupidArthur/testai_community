import { apiClient } from './client'
import type {
  WorkDailyAudit,
  WorkDailyAuditRequest,
  WorkDailyListItem,
  WorkDailyReport,
  WorkDailySubmitRequest,
} from '../types/models'

export const workDailyApi = {
  list: (params?: { report_date?: string; user_id?: number; limit?: number }) =>
    apiClient.get<WorkDailyListItem[]>('/work-daily', { params }),

  get: (reportId: string) => apiClient.get<WorkDailyReport>(`/work-daily/${reportId}`),

  audit: (data: WorkDailyAuditRequest) =>
    apiClient.post<{ audit: WorkDailyAudit; skill_version_id?: string | null }>(
      '/work-daily/audit',
      data,
      { timeout: 120000 },
    ),

  submit: (data: WorkDailySubmitRequest) =>
    apiClient.post<WorkDailyReport>('/work-daily', data, { timeout: 120000 }),

  exportByDate: (report_date: string) =>
    apiClient.get<WorkDailyReport[]>('/work-daily/export', { params: { report_date } }),

  downloadZip: async (params: {
    start_date: string
    end_date: string
    user_id?: number
  }) => {
    const res = await apiClient.get('/work-daily/download', {
      params,
      responseType: 'blob',
    })
    const blob = new Blob([res.data], { type: 'application/zip' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `work_daily_${params.start_date}_${params.end_date}.zip`
    a.click()
    window.URL.revokeObjectURL(url)
  },
}

/** @deprecated 使用 workDailyApi */
export const dailyReportApi = workDailyApi
