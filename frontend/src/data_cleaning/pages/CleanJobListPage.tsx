import { useState } from 'react'
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import { FilterOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { dataCleaningApi } from '../../shared/api/data-cleaning'
import { knowledgeBaseApi } from '../../shared/api/knowledge-base'

const { Title, Text } = Typography

const STATUS_COLOR: Record<string, string> = {
  uploaded: 'default',
  processing: 'processing',
  pending_review: 'warning',
  approved: 'success',
  failed: 'error',
}

const DOC_TYPES = [
  { value: 'prd', label: 'PRD / 需求文档' },
  { value: 'performance_report', label: '性能测试报告' },
  { value: 'mixed', label: '混合大文档' },
  { value: 'general', label: '通用' },
]

interface CleanJobListPageProps {
  /** 嵌入知识库 Hub 时隐藏页头、不选目标库 */
  embedded?: boolean
  kbId?: string
  reviewPathPrefix?: string
}

export default function CleanJobListPage({
  embedded = false,
  kbId: fixedKbId,
  reviewPathPrefix = '/data-cleaning',
}: CleanJobListPageProps = {}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [form] = Form.useForm()

  const { data: bases = [] } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: () => knowledgeBaseApi.listBases().then((r) => r.data),
    enabled: !embedded,
  })

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['clean-jobs', fixedKbId ?? 'all'],
    queryFn: () => dataCleaningApi.listJobs(fixedKbId).then((r) => r.data),
    refetchInterval: (q) => {
      const list = q.state.data as { status: string }[] | undefined
      if (list?.some((j) => j.status === 'uploaded' || j.status === 'processing')) return 3000
      return false
    },
  })

  const createMutation = useMutation({
    mutationFn: async (values: Record<string, string>) => {
      if (!file) throw new Error('请选择文件')
      const fd = new FormData()
      fd.append('file', file)
      const targetKbId = embedded ? fixedKbId : values.kb_id
      if (targetKbId) fd.append('kb_id', targetKbId)
      fd.append('doc_type', values.doc_type)
      fd.append('product', values.product || '')
      fd.append('version', values.version || '')
      fd.append('environment', values.environment || '')
      fd.append('note', values.note || '')
      return dataCleaningApi.createJob(fd).then((r) => r.data)
    },
    onSuccess: (job) => {
      message.success('已创建清洗任务，后台处理中')
      setOpen(false)
      setFile(null)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['clean-jobs'] })
      navigate(`${reviewPathPrefix}/${job.id}`)
    },
    onError: (err: any) => message.error(err.response?.data?.detail || '创建失败'),
  })

  const columns = [
    { title: '文件', dataIndex: 'filename', ellipsis: true },
    ...(!embedded
      ? [
          {
            title: '目标知识库',
            render: (_: unknown, r: { kb_id: string }) =>
              bases.find((b) => b.id === r.kb_id)?.name || r.kb_id.slice(0, 8),
          },
        ]
      : []),
    { title: '类型', dataIndex: 'doc_type', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 130,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: '段落数', dataIndex: 'paragraph_count', width: 90 },
    { title: '上传者', dataIndex: 'username', width: 100 },
    { title: '时间', dataIndex: 'created_at', width: 170, render: (t: string) => t?.slice(0, 16) },
  ]

  return (
    <div style={{ maxWidth: embedded ? undefined : 1200, margin: embedded ? undefined : '0 auto' }}>
      {!embedded && (
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <FilterOutlined style={{ color: 'var(--color-primary)', marginRight: 8 }} />
            数据清洗
          </Title>
          <Text type="secondary">入库前质检：提炼精华、检测冲突，确认后写入知识库</Text>
        </div>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
            新建清洗任务
          </Button>
        </Space>
      </div>
      )}

      {embedded && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16, gap: 8 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            data-testid="kb-clean-new"
            onClick={() => setOpen(true)}
          >
            新建清洗任务
          </Button>
        </div>
      )}

      <Card>
        <Table
          rowKey="id"
          data-testid="kb-clean-table"
          loading={isLoading}
          dataSource={jobs}
          locale={{ emptyText: <Empty description="暂无清洗任务" /> }}
          onRow={(r) => ({
            onClick: () => navigate(`${reviewPathPrefix}/${r.id}`),
            style: { cursor: 'pointer' },
          })}
          columns={columns}
        />
      </Card>

      <Modal
        title="新建清洗任务"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        okText="确定"
        cancelText="取消"
        confirmLoading={createMutation.isPending}
        width={560}
        data-testid="kb-clean-modal"
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          {embedded
            ? '上传文档后系统自动切分提炼；请在审核页确认并批准入库。'
            : '上传时选择文档类型；系统切分提炼后请在审核页确认。'}
        </Text>
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => createMutation.mutate(v)}
          initialValues={{ doc_type: 'general', kb_id: fixedKbId }}
        >
          {!embedded && (
            <Form.Item name="kb_id" label="目标知识库" rules={[{ required: true }]}>
              <Select options={bases.map((b) => ({ value: b.id, label: b.name }))} placeholder="选择知识库" />
            </Form.Item>
          )}
          <Form.Item name="doc_type" label="文档类型" rules={[{ required: true }]}>
            <Select options={DOC_TYPES} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="product" label="产品/项目">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="version" label="版本">
                <Input placeholder="如 v2.3" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="environment" label="环境">
            <Input placeholder="production / test，可选" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label="文档文件" required>
            <Upload
              data-testid="kb-clean-upload"
              beforeUpload={(f) => {
                setFile(f)
                return false
              }}
              maxCount={1}
              onRemove={() => setFile(null)}
            >
              <Button icon={<UploadOutlined />} data-testid="kb-clean-upload-btn">
                选择文件
              </Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
