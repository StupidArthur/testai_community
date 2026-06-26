import { apiClient } from './client'

export interface Alignment {
  relation: string
  confidence: number
  topic: string
  new_claim: string
  old_claim: string
  recommended_action: string
  reason: string
  chunk_id?: string | null
  old_ku_id?: string | null
  old_filename: string
  old_snippet: string
  distance?: number | null
}

export interface ParagraphUnit {
  id: string
  job_id: string
  seq: number
  section_path: string
  raw_text: string
  essence_markdown: string
  anchor_ids: string[]
  suggested_anchors: { anchor_id: string; label: string; score: number; match_type: string }[]
  scope: Record<string, string>
  alignments: Alignment[]
  review_status: string
  review_action: string
  ku_id?: string | null
  skip_reason: string
}

export interface CleanJob {
  id: string
  kb_id: string
  user_id: number
  username: string
  filename: string
  file_size: number
  doc_type: string
  product: string
  version: string
  environment: string
  note: string
  status: string
  error?: string | null
  paragraph_count: number
  created_at: string
  updated_at: string
}

export interface CleanJobDetail extends CleanJob {
  paragraphs: ParagraphUnit[]
}

export interface AnchorNode {
  id: string
  label: string
  parent_id?: string | null
  synonyms: string[]
  description: string
  sort_order: number
  enabled: boolean
}

export const dataCleaningApi = {
  listJobs: (kbId?: string) =>
    apiClient.get<CleanJob[]>('/data-cleaning/jobs', { params: kbId ? { kb_id: kbId } : {} }),

  createJob: (form: FormData) =>
    apiClient.post<CleanJob>('/data-cleaning/jobs', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }),

  getJob: (jobId: string) => apiClient.get<CleanJobDetail>(`/data-cleaning/jobs/${jobId}`),

  reprocessJob: (jobId: string) =>
    apiClient.post<CleanJob>(`/data-cleaning/jobs/${jobId}/reprocess`),

  updateParagraph: (
    jobId: string,
    paragraphId: string,
    data: Partial<{
      essence_markdown: string
      anchor_ids: string[]
      scope: Record<string, string>
      review_status: string
      review_action: string
      skip_reason: string
    }>,
  ) => apiClient.patch<ParagraphUnit>(`/data-cleaning/jobs/${jobId}/paragraphs/${paragraphId}`, data),

  approveJob: (jobId: string, paragraphIds?: string[], timeoutMs = 300_000) =>
    apiClient.post<{ approved_count: number; skipped_count: number; ku_ids: string[] }>(
      `/data-cleaning/jobs/${jobId}/approve`,
      paragraphIds ? { paragraph_ids: paragraphIds } : {},
      { timeout: timeoutMs },
    ),

  listAnchors: () => apiClient.get<AnchorNode[]>('/data-cleaning/anchors'),

  createAnchor: (data: {
    id: string
    label: string
    parent_id?: string | null
    synonyms?: string[]
    description?: string
    sort_order?: number
  }) => apiClient.post<AnchorNode>('/data-cleaning/anchors', data),

  updateAnchor: (anchorId: string, data: Partial<AnchorNode>) =>
    apiClient.patch<AnchorNode>(`/data-cleaning/anchors/${anchorId}`, data),
}
