import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
  Breadcrumb,
} from 'antd'
import { CheckOutlined, DatabaseOutlined, WarningOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { dataCleaningApi, type ParagraphUnit } from '../../shared/api/data-cleaning'

const { Title, Text, Paragraph } = Typography

const ACTION_OPTIONS = [
  { value: 'add', label: '新增入库' },
  { value: 'supersede', label: '替换旧知识' },
  { value: 'coexist', label: '并存（不同版本/环境）' },
  { value: 'skip', label: '跳过不入库' },
]

const ACTION_LABEL: Record<string, string> = Object.fromEntries(
  ACTION_OPTIONS.map((o) => [o.value, o.label]),
)

function relationTag(relation: string) {
  const map: Record<string, { color: string; label: string }> = {
    contradiction: { color: 'red', label: '逻辑冲突' },
    update: { color: 'orange', label: '版本更新' },
    scoped_difference: { color: 'blue', label: '环境差异' },
    same_fact: { color: 'default', label: '重复' },
    possible_related: { color: 'gold', label: '可能相关' },
  }
  const m = map[relation] || { color: 'default', label: relation }
  return <Tag color={m.color}>{m.label}</Tag>
}

export default function CleanJobReviewPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [batchAction, setBatchAction] = useState<string>('add')

  const { data: job, isLoading } = useQuery({
    queryKey: ['clean-job', jobId],
    queryFn: () => dataCleaningApi.getJob(jobId!).then((r) => r.data),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status
      if (s === 'uploaded' || s === 'processing') return 3000
      return false
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ pid, data }: { pid: string; data: Parameters<typeof dataCleaningApi.updateParagraph>[2] }) =>
      dataCleaningApi.updateParagraph(jobId!, pid, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clean-job', jobId] })
    },
    onError: (err: any) => message.error(err.response?.data?.detail || '保存失败'),
  })

  const batchActionMutation = useMutation({
    mutationFn: (action: string) => dataCleaningApi.batchReviewAction(jobId!, action),
    onSuccess: (res) => {
      message.success(`已将 ${res.data.updated_count} 段统一设为「${ACTION_LABEL[res.data.review_action] || res.data.review_action}」`)
      queryClient.invalidateQueries({ queryKey: ['clean-job', jobId] })
    },
    onError: (err: any) => message.error(err.response?.data?.detail || '批量修改失败'),
  })

  const approveMutation = useMutation({
    mutationFn: () => {
      const n = job?.paragraph_count || 10
      // 每段约 5s 向量写入，84 段约 7 分钟；并行 4 路后约 2 分钟，留足余量
      const timeoutMs = Math.min(1_200_000, Math.max(300_000, n * 5_000))
      return dataCleaningApi.approveJob(jobId!, undefined, timeoutMs)
    },
    onSuccess: (res) => {
      message.success(`已入库 ${res.data.approved_count} 条，跳过 ${res.data.skipped_count} 条`)
      queryClient.invalidateQueries({ queryKey: ['clean-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['clean-job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-base'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-base-default'] })
      navigate('/knowledge-base?tab=chat')
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        message.error(
          '批准请求超时：任务可能尚未完成。请确认 Ollama 已启动后刷新页面查看状态，必要时再次点击批准。',
          8,
        )
        queryClient.invalidateQueries({ queryKey: ['clean-job', jobId] })
        return
      }
      message.error(detail || '批准失败', 8)
    },
  })

  const reprocessMutation = useMutation({
    mutationFn: () => dataCleaningApi.reprocessJob(jobId!),
    onSuccess: () => {
      message.success('已重新入队，请稍候刷新')
      queryClient.invalidateQueries({ queryKey: ['clean-job', jobId] })
    },
    onError: (err: any) => message.error(err.response?.data?.detail || '重新处理失败'),
  })

  const conflictCount = useMemo(
    () => job?.paragraphs.filter((p) => p.alignments.some((a) => a.relation === 'contradiction')).length ?? 0,
    [job],
  )

  const renderParagraph = (p: ParagraphUnit) => {
    const essence = editing[p.id] ?? p.essence_markdown
    const hasConflict = p.alignments.some((a) => a.relation === 'contradiction')
    return {
      key: p.id,
      label: (
        <Space wrap>
          <Text strong>{p.section_path || `段落 ${p.seq + 1}`}</Text>
          {hasConflict && <Tag color="red" icon={<WarningOutlined />}>冲突</Tag>}
          <Tag>{ACTION_LABEL[p.review_action] || p.review_action}</Tag>
        </Space>
      ),
      children: (
        <div>
          {p.alignments.length > 0 && (
            <Alert
              type={hasConflict ? 'error' : 'info'}
              showIcon
              style={{ marginBottom: 12 }}
              message="库内对比"
              description={
                <div>
                  {p.alignments.map((a, i) => (
                    <div key={i} style={{ marginBottom: 8 }}>
                      {relationTag(a.relation)}
                      <Text> {a.topic} — {a.reason}</Text>
                      {a.old_snippet && (
                        <Paragraph type="secondary" style={{ fontSize: 12, margin: '4px 0 0' }}>
                          旧：{a.old_snippet}
                        </Paragraph>
                      )}
                    </div>
                  ))}
                </div>
              }
            />
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>正文（可编辑）</Text>
          <Input.TextArea
            rows={6}
            value={essence}
            onChange={(e) => setEditing((m) => ({ ...m, [p.id]: e.target.value }))}
            onBlur={() => {
              const v = editing[p.id]
              if (v !== undefined && v !== p.essence_markdown) {
                updateMutation.mutate({ pid: p.id, data: { essence_markdown: v } })
              }
            }}
            disabled={job?.status !== 'pending_review'}
            style={{ marginTop: 4, marginBottom: 12 }}
          />
          <Space wrap>
            <span>入库操作：</span>
            <Select
              style={{ width: 200 }}
              value={p.review_action}
              disabled={job?.status !== 'pending_review'}
              options={ACTION_OPTIONS}
              onChange={(v) => updateMutation.mutate({ pid: p.id, data: { review_action: v } })}
            />
          </Space>
        </div>
      ),
    }
  }

  if (isLoading || !job) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <span style={{ cursor: 'pointer' }} onClick={() => navigate('/knowledge-base?tab=clean')}>清洗入库</span> },
          { title: job.filename },
        ]}
      />

      <Card style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginTop: 0 }}>{job.filename}</Title>
        <Space wrap>
          <Tag>{job.doc_type}</Tag>
          <Tag color={job.status === 'pending_review' ? 'warning' : 'default'}>{job.status}</Tag>
          {job.product && <Tag>产品: {job.product}</Tag>}
          {job.version && <Tag>版本: {job.version}</Tag>}
          {job.environment && <Tag>环境: {job.environment}</Tag>}
          <Text type="secondary">共 {job.paragraph_count} 段</Text>
        </Space>
        {job.error && <Alert type="error" message={job.error} style={{ marginTop: 12 }} />}
        {(job.status === 'uploaded' || job.status === 'processing') && (
          <Alert type="info" message="后台处理中，请稍候…" style={{ marginTop: 12 }} showIcon />
        )}
        {job.status === 'pending_review' && job.paragraph_count === 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 12 }}
            message="未生成可审核段落"
            description="文档内容过短或格式无法切分，请补充内容后重新上传。"
          />
        )}
        {job.status === 'pending_review' && job.paragraph_count > 0 && (
          <div style={{ marginTop: 16 }}>
            {conflictCount > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message={`${conflictCount} 个段落存在逻辑冲突，请为每段选择操作后再批准入库`}
              />
            )}
            <Space wrap style={{ marginBottom: 12 }}>
              <span>批量入库操作：</span>
              <Select
                style={{ width: 220 }}
                value={batchAction}
                options={ACTION_OPTIONS}
                onChange={setBatchAction}
              />
              <Button
                loading={batchActionMutation.isPending}
                onClick={() => batchActionMutation.mutate(batchAction)}
              >
                应用到全部段落
              </Button>
            </Space>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              data-testid="kb-clean-approve"
              loading={approveMutation.isPending}
              onClick={() => approveMutation.mutate()}
            >
              批准入库
            </Button>
            <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
              共 {job.paragraph_count} 段，需调用本机 Ollama（bge-m3）写向量，请保持页面等待完成（约 1～5 分钟）。
            </Text>
            <Button style={{ marginLeft: 8 }} icon={<DatabaseOutlined />} onClick={() => navigate('/knowledge-base')}>
              打开知识库
            </Button>
          </div>
        )}
        {job.status === 'approved' && (
          <Alert type="success" message="已批准入库" style={{ marginTop: 12 }} showIcon />
        )}
      </Card>

      {(job.status === 'processing' || job.status === 'uploaded') && job.paragraph_count > 0 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`后台处理中：${job.paragraphs.length}/${job.paragraph_count} 段已完成（每段约 5–15 秒，请勿频繁重启后端）`}
        />
      )}

      {job.paragraphs.length === 0 ? (
        <Card>
          <Text type="secondary">
            {job.status === 'processing' || job.status === 'uploaded'
              ? job.status === 'processing' && job.paragraph_count > 0
                ? `处理中：已完成 ${job.paragraphs.length}/${job.paragraph_count} 段（每段调用 LLM，请耐心等待）…`
                : '处理中，请稍候…'
              : '暂无段落。Word 文档若每段较短，旧版切分规则可能全部过滤；请点「重新处理」或重新上传。'}
          </Text>
          {(job.status === 'pending_review' || job.status === 'failed') && (
            <Button
              style={{ marginTop: 12 }}
              loading={reprocessMutation.isPending}
              onClick={() => reprocessMutation.mutate()}
            >
              重新处理
            </Button>
          )}
        </Card>
      ) : (
        <Collapse items={job.paragraphs.map(renderParagraph)} defaultActiveKey={job.paragraphs.slice(0, 3).map((p) => p.id)} />
      )}
    </div>
  )
}
