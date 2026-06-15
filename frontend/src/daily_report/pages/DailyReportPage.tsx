import { useMemo, useState, useEffect } from 'react'
import {
  Card,
  Typography,
  Input,
  Button,
  DatePicker,
  Table,
  Tag,
  Space,
  message,
  Modal,
  Descriptions,
  Alert,
  Empty,
  Spin,
  Select,
  Row,
  Col,
  List,
  Divider,
  Progress,
} from 'antd'
import {
  FileTextOutlined,
  PlusOutlined,
  EyeOutlined,
  AuditOutlined,
  DownloadOutlined,
  ExportOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { workDailyApi } from '../../shared/api/daily-report'
import { useCurrentUser, isAdmin as checkAdmin } from '../../shared/hooks/useAuth'
import type { WorkDailyAudit, WorkDailyListItem, WorkDailyReport } from '../../shared/types/models'

const { Title, Text, Paragraph } = Typography

const REPORT_ROLES = ['测试工程师', '测试负责人'] as const
const MAX_DAYS_BACK = 7

const PLACEHOLDER = `请用纯文本描述今日工作。

必填：
1. 今天做了什么（可宽泛也可详细）
2. 每项工作投入了多少时间（如：功能测试 4h）

选填：对工作流程、协作方式的反馈与建议。`

function disabledDate(current: Dayjs) {
  const today = dayjs().endOf('day')
  const earliest = dayjs().subtract(MAX_DAYS_BACK, 'day').startOf('day')
  return current.isAfter(today) || current.isBefore(earliest)
}

function AuditResultBody({ audit }: { audit: WorkDailyAudit }) {
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <div>
        {audit.valid ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            信息较完整
          </Tag>
        ) : (
          <Tag icon={<WarningOutlined />} color="warning">
            建议补充
          </Tag>
        )}
        {audit.summary && (
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            {audit.summary}
          </Paragraph>
        )}
      </div>

      {(audit.validation_issues.length > 0 || audit.suggestions.length > 0) && (
        <Alert
          type="warning"
          showIcon
          message="审核建议"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {[...audit.validation_issues, ...audit.suggestions].map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          }
        />
      )}

      {audit.missing_dimensions.length > 0 && (
        <Alert
          type="info"
          showIcon
          message="可能缺失的工作维度"
          description={audit.missing_dimensions.join('、')}
        />
      )}

      {audit.work_items.length > 0 && (
        <div>
          <Text strong>工作项与占比</Text>
          <List
            size="small"
            style={{ marginTop: 8 }}
            dataSource={audit.work_items}
            renderItem={(item) => (
              <List.Item>
                <Text>
                  {item.category || '未分类'} — {item.hours}h
                  {item.ratio > 0 ? ` (${(item.ratio * 100).toFixed(0)}%)` : ''}
                  {item.description ? `：${item.description}` : ''}
                </Text>
              </List.Item>
            )}
          />
          <Text type="secondary">合计约 {audit.total_hours.toFixed(1)} 小时</Text>
        </div>
      )}

      {audit.dimension_coverage.length > 0 && (
        <div>
          <Text strong>已覆盖维度</Text>
          <div style={{ marginTop: 4 }}>
            {audit.dimension_coverage.map((d) => (
              <Tag key={d}>{d}</Tag>
            ))}
          </div>
        </div>
      )}

      {audit.feedback && (
        <div>
          <Text strong>流程反馈（原文摘录）</Text>
          <Paragraph style={{ marginBottom: 0 }}>{audit.feedback}</Paragraph>
        </div>
      )}
    </Space>
  )
}

function AuditPanel({
  audit,
  loading,
  progress,
}: {
  audit: WorkDailyAudit | null
  loading: boolean
  progress: number
}) {
  if (loading) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Progress percent={Math.round(progress)} status="active" />
        <Text type="secondary" style={{ textAlign: 'center', display: 'block' }}>
          AI 审核中，正在调用 skill-hub master 解析工作维度与工时…
        </Text>
        {audit ? (
          <>
            <Alert type="info" showIcon message="以下为上次审核结果，新结果返回后将自动更新" />
            <AuditResultBody audit={audit} />
          </>
        ) : null}
      </Space>
    )
  }
  if (!audit) {
    return (
      <Empty
        description="点击左侧「审核」后，此处展示工作维度、工时占比与补充建议"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }

  return <AuditResultBody audit={audit} />
}

export default function DailyReportPage() {
  const queryClient = useQueryClient()
  const user = useCurrentUser()
  const isAdmin = checkAdmin(user)

  const [createOpen, setCreateOpen] = useState(false)
  const [reportDate, setReportDate] = useState<Dayjs>(dayjs())
  const [reportRole, setReportRole] = useState<string>(REPORT_ROLES[0])
  const [rawText, setRawText] = useState('')
  const [auditResult, setAuditResult] = useState<WorkDailyAudit | null>(null)
  const [auditProgress, setAuditProgress] = useState(0)

  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<WorkDailyReport | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [exportDate, setExportDate] = useState<Dayjs>(dayjs())
  const [dlStart, setDlStart] = useState<Dayjs>(dayjs())
  const [dlEnd, setDlEnd] = useState<Dayjs>(dayjs())
  const [dlUserId, setDlUserId] = useState<number | undefined>()
  const [dlLoading, setDlLoading] = useState(false)

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['work-daily'],
    queryFn: () => workDailyApi.list({ limit: 100 }).then((r) => r.data),
  })

  const userOptions = useMemo(() => {
    const map = new Map<number, string>()
    reports.forEach((r) => map.set(r.user_id, r.username))
    return Array.from(map.entries()).map(([id, name]) => ({ value: id, label: name }))
  }, [reports])

  const auditMutation = useMutation({
    mutationFn: () =>
      workDailyApi
        .audit({
          report_date: reportDate.format('YYYY-MM-DD'),
          report_role: reportRole,
          raw_text: rawText,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      setAuditProgress(100)
      setAuditResult(data.audit)
      message.success('审核完成')
    },
    onError: (err: any) => {
      setAuditProgress(0)
      message.error(err.response?.data?.detail || err.message || '审核失败')
    },
  })

  useEffect(() => {
    if (!auditMutation.isPending) return
    setAuditProgress(8)
    const timer = setInterval(() => {
      setAuditProgress((p) => (p >= 92 ? p : p + 4 + Math.random() * 6))
    }, 700)
    return () => clearInterval(timer)
  }, [auditMutation.isPending])

  const isAuditing = auditMutation.isPending

  const submitMutation = useMutation({
    mutationFn: () =>
      workDailyApi
        .submit({
          report_date: reportDate.format('YYYY-MM-DD'),
          report_role: reportRole,
          raw_text: rawText,
          audit: auditResult,
        })
        .then((r) => r.data),
    onSuccess: () => {
      message.success('日报已提交')
      setCreateOpen(false)
      setRawText('')
      setAuditResult(null)
      queryClient.invalidateQueries({ queryKey: ['work-daily'] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || err.message || '提交失败')
    },
  })

  const resetCreateForm = () => {
    setReportDate(dayjs())
    setReportRole(REPORT_ROLES[0])
    setRawText('')
    setAuditResult(null)
  }

  const openCreate = () => {
    resetCreateForm()
    setCreateOpen(true)
  }

  const handleAudit = () => {
    if (!rawText.trim()) {
      message.warning('请填写日报内容')
      return
    }
    auditMutation.mutate()
  }

  const handleSubmit = () => {
    if (!rawText.trim()) {
      message.warning('请填写日报内容')
      return
    }
    submitMutation.mutate()
  }

  const openDetail = async (row: WorkDailyListItem) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
    try {
      const res = await workDailyApi.get(row.id)
      setDetail(res.data)
    } catch (err: any) {
      message.error(err.response?.data?.detail || '加载详情失败')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleExport = async () => {
    try {
      const res = await workDailyApi.exportByDate(exportDate.format('YYYY-MM-DD'))
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `work_daily_export_${exportDate.format('YYYY-MM-DD')}.json`
      a.click()
      window.URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (err: any) {
      message.error(err.response?.data?.detail || '导出失败')
    }
  }

  const handleDownload = async () => {
    setDlLoading(true)
    try {
      await workDailyApi.downloadZip({
        start_date: dlStart.format('YYYY-MM-DD'),
        end_date: dlEnd.format('YYYY-MM-DD'),
        user_id: isAdmin ? dlUserId : undefined,
      })
      message.success('下载已开始')
    } catch (err: any) {
      message.error(err.response?.data?.detail || '下载失败')
    } finally {
      setDlLoading(false)
    }
  }

  const columns = [
    {
      title: '日期',
      dataIndex: 'report_date',
      key: 'report_date',
      width: 110,
    },
    ...(isAdmin
      ? [{ title: '提交人', dataIndex: 'username', key: 'username', width: 100 }]
      : []),
    {
      title: '角色',
      dataIndex: 'report_role',
      key: 'report_role',
      width: 110,
    },
    {
      title: '内容摘要',
      dataIndex: 'summary_preview',
      key: 'summary_preview',
      ellipsis: true,
    },
    {
      title: '总工时(h)',
      dataIndex: 'total_hours',
      key: 'total_hours',
      width: 100,
      render: (v: number) => (v ?? 0).toFixed(1),
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, row: WorkDailyListItem) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(row)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', position: 'relative', minHeight: '100%' }}>
      <div
        style={{
          marginBottom: 24,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 16,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, color: 'var(--color-text)' }}>
            <FileTextOutlined style={{ marginRight: 8, color: 'var(--color-primary)' }} />
            工作日报
          </Title>
          <Text type="secondary">
            记录每日工作与投入时间；可先审核再提交，也可直接提交。同天可多次提交。
          </Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建日报
        </Button>
      </div>

      {isAdmin && (
        <Card
          size="small"
          title="管理员工具"
          style={{ marginBottom: 16, border: '1px solid var(--color-border)' }}
        >
          <Space wrap>
            <DatePicker value={exportDate} onChange={(d) => d && setExportDate(d)} allowClear={false} />
            <Button icon={<ExportOutlined />} onClick={handleExport}>
              按日期导出 JSON
            </Button>
            <Divider type="vertical" />
            <DatePicker
              value={dlStart}
              onChange={(d) => d && setDlStart(d)}
              allowClear={false}
              placeholder="开始日期"
            />
            <DatePicker
              value={dlEnd}
              onChange={(d) => d && setDlEnd(d)}
              allowClear={false}
              placeholder="结束日期"
            />
            <Select
              allowClear
              placeholder="全部用户"
              style={{ width: 140 }}
              options={userOptions}
              value={dlUserId}
              onChange={setDlUserId}
            />
            <Button icon={<DownloadOutlined />} loading={dlLoading} onClick={handleDownload}>
              下载原始 txt
            </Button>
          </Space>
        </Card>
      )}

      {!isAdmin && (
        <div style={{ marginBottom: 16, textAlign: 'right' }}>
          <Space>
            <DatePicker value={dlStart} onChange={(d) => d && setDlStart(d)} allowClear={false} />
            <DatePicker value={dlEnd} onChange={(d) => d && setDlEnd(d)} allowClear={false} />
            <Button icon={<DownloadOutlined />} loading={dlLoading} onClick={handleDownload}>
              下载我的原始日报
            </Button>
          </Space>
        </div>
      )}

      <Card
        title={isAdmin ? '全部日报记录' : '我的日报记录'}
        style={{ border: '1px solid var(--color-border)', background: 'var(--color-bg)' }}
      >
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : reports.length === 0 ? (
          <Empty description="暂无日报，点击右上角新建" />
        ) : (
          <Table rowKey="id" columns={columns} dataSource={reports} pagination={{ pageSize: 10 }} />
        )}
      </Card>

      <Modal
        title="新建工作日报"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        footer={null}
        width={960}
        destroyOnHidden
      >
        <Row gutter={16}>
          <Col span={12}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Alert
                type="info"
                showIcon
                message="填写要求"
                description={
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    <li>必填：今天做了什么、投入多少时间</li>
                    <li>选填：对流程与协作的反馈</li>
                    <li>可补交最近 {MAX_DAYS_BACK} 天内的日报</li>
                  </ul>
                }
              />
              <div>
                <Text strong>日报日期</Text>
                <DatePicker
                  value={reportDate}
                  onChange={(d) => d && setReportDate(d)}
                  disabledDate={disabledDate}
                  disabled={isAuditing}
                  allowClear={false}
                  style={{ width: '100%', marginTop: 8 }}
                />
              </div>
              <div>
                <Text strong>日报角色</Text>
                <Select
                  value={reportRole}
                  onChange={setReportRole}
                  disabled={isAuditing}
                  options={REPORT_ROLES.map((r) => ({ value: r, label: r }))}
                  style={{ width: '100%', marginTop: 8 }}
                />
              </div>
              <div>
                <Text strong>日报内容（纯文本）</Text>
                <Input.TextArea
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  disabled={isAuditing}
                  placeholder={PLACEHOLDER}
                  autoSize={{ minRows: 10, maxRows: 16 }}
                  maxLength={8000}
                  showCount
                  style={{ marginTop: 8 }}
                />
              </div>
              <Space>
                <Button
                  icon={<AuditOutlined />}
                  loading={isAuditing}
                  onClick={handleAudit}
                >
                  审核
                </Button>
                <Button
                  type="primary"
                  loading={submitMutation.isPending}
                  disabled={isAuditing}
                  onClick={handleSubmit}
                >
                  提交
                </Button>
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                审核过程中内容不可编辑；修改后请重新审核。也可忽略审核结果直接提交。
              </Text>
            </Space>
          </Col>
          <Col span={12}>
            <Card
              size="small"
              title="审核结果"
              style={{ minHeight: 420, border: '1px solid var(--color-border)' }}
            >
              <AuditPanel audit={auditResult} loading={isAuditing} progress={auditProgress} />
            </Card>
          </Col>
        </Row>
      </Modal>

      <Modal
        title="日报详情"
        open={detailOpen}
        onCancel={() => {
          setDetailOpen(false)
          setDetail(null)
        }}
        footer={null}
        width={720}
        destroyOnHidden
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : detail ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {!detail.audit.valid && detail.audit.validation_issues.length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="审核提示"
                description={
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {detail.audit.validation_issues.map((i) => (
                      <li key={i}>{i}</li>
                    ))}
                  </ul>
                }
              />
            )}
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="日期">{detail.report_date}</Descriptions.Item>
              <Descriptions.Item label="角色">{detail.report_role}</Descriptions.Item>
              <Descriptions.Item label="提交人">{detail.username}</Descriptions.Item>
              <Descriptions.Item label="总工时">{detail.audit.total_hours} h</Descriptions.Item>
            </Descriptions>
            {detail.audit.work_items.length > 0 && (
              <div>
                <Text strong>工作项</Text>
                <ul style={{ marginTop: 8 }}>
                  {detail.audit.work_items.map((w) => (
                    <li key={`${w.category}-${w.hours}`}>
                      {w.category} — {w.hours}h：{w.description || '—'}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {detail.audit.summary && (
              <div>
                <Text strong>AI 摘要</Text>
                <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>{detail.audit.summary}</Paragraph>
              </div>
            )}
            <div>
              <Text strong>原始文本</Text>
              <Paragraph
                style={{
                  background: 'var(--color-bg-secondary)',
                  padding: 12,
                  borderRadius: 4,
                  whiteSpace: 'pre-wrap',
                  maxHeight: 240,
                  overflow: 'auto',
                }}
              >
                {detail.raw_text}
              </Paragraph>
            </div>
          </Space>
        ) : null}
      </Modal>

      <Text
        type="secondary"
        style={{ position: 'absolute', right: 0, bottom: -28, fontSize: 11 }}
      >
        designed by @yuzechao
      </Text>
    </div>
  )
}
