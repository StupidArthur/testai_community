import { useNavigate } from 'react-router-dom'
import { Button, Space, Typography, Select, Tag, Modal } from 'antd'
import { type ProColumns, ProTable } from '@ant-design/pro-components'
import { DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { StatusBadge } from './StatusBadge'
import type { JobView } from '../../shared/api/translate-jobs'
import { cancelJob, getDownloadUrl, deleteJobRecord } from '../../shared/api/translate-jobs'
import { parseApiErrorMessage } from '../../shared/api/translate-client'
import { useCurrentUser, isAdmin as checkAdmin } from '../../shared/hooks/useAuth'
import { message } from 'antd'
import { useMemo, useState } from 'react'

const { Text } = Typography

interface JobListProps {
  jobs: JobView[]
  isLoading?: boolean
  refetch?: () => void
}

const PHASE_LABELS: Record<string, string> = {
  preprocess: '预处理',
  phase1: '阶段一',
  phase2: '阶段二',
  phase4: '阶段四',
  finalize: '打包结果',
}

const STATUS_OPTIONS = [
  { text: '排队中', value: 'queued' },
  { text: '运行中', value: 'running' },
  { text: '已完成', value: 'completed' },
  { text: '失败', value: 'failed' },
  { text: '已取消', value: 'cancelled' },
]

export function JobList({ jobs, isLoading, refetch }: JobListProps) {
  const navigate = useNavigate()
  const currentUser = useCurrentUser()
  const isAdmin = checkAdmin(currentUser)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deletingJob, setDeletingJob] = useState<JobView | null>(null)

  const usernameOptions = useMemo(() => {
    const set = new Set(jobs.map((j) => j.username).filter(Boolean))
    return Array.from(set).map((u) => ({ text: u, value: u }))
  }, [jobs])

  const columns: ProColumns<JobView>[] = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      hideInSearch: false,
      fieldProps: { placeholder: '搜索任务名称' },
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      width: 120,
      hideInSearch: false,
      valueType: 'select',
      fieldProps: { placeholder: '选择用户' },
      request: async () => usernameOptions,
      filters: usernameOptions,
      onFilter: (value, row) => row.username === value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      hideInSearch: false,
      valueType: 'select',
      fieldProps: { placeholder: '选择状态' },
      valueEnum: {
        queued: { text: '排队中' },
        running: { text: '运行中' },
        completed: { text: '已完成' },
        failed: { text: '失败' },
        cancelled: { text: '已取消' },
      },
      filters: STATUS_OPTIONS,
      onFilter: (value, row) => row.status === value,
      render: (_, row) => <StatusBadge status={row.status} />,
    },
    {
      title: '阶段',
      dataIndex: 'current_phase',
      key: 'current_phase',
      width: 100,
      hideInSearch: true,
      render: (_, row) => (PHASE_LABELS[row.current_phase] ?? row.current_phase) || '-',
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.message || '-'}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      hideInSearch: true,
      render: (_, row) => (
        <Space size={4}>
          <Button
            size="small"
            type="link"
            onClick={() => navigate(`/translate/jobs/${row.job_id}`)}
          >
            详情
          </Button>
          {row.status === 'completed' && (
            <Button
              size="small"
              icon={<DownloadOutlined />}
              onClick={async () => {
                const url = await getDownloadUrl(row.job_id)
                window.open(url, '_blank')
              }}
            >
              下载
            </Button>
          )}
          {(row.status === 'queued' || row.status === 'running') && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={async () => {
                try {
                  await cancelJob(row.job_id)
                  message.success('已取消')
                  refetch?.()
                } catch {
                  message.error('取消失败')
                }
              }}
            >
              取消
            </Button>
          )}
          {isAdmin && row.status !== 'queued' && row.status !== 'running' && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => {
                setDeletingJob(row)
                setDeleteModalOpen(true)
              }}
            >
              删除
            </Button>
          )}
        </Space>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      hideInSearch: true,
      render: (_, row) =>
        new Date(row.created_at).toLocaleString('zh-CN', {
          timeZone: 'Asia/Shanghai',
        }),
    },
  ]

  return (
    <>
    <ProTable
      columns={columns}
      dataSource={jobs}
      rowKey="job_id"
      loading={isLoading}
      search={{
        filterType: 'light',
        layout: 'inline',
        defaultCollapsed: false,
      }}
      toolBarRender={false}
      pagination={{
        defaultPageSize: 15,
        pageSizeOptions: [10, 15, 30, 50],
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 条`,
      }}
      options={false}
      scroll={{ y: 'calc(100vh - 280px)' }}
      style={{ background: 'transparent' }}
    />

    <Modal
      title="确认删除翻译记录"
      open={deleteModalOpen}
      onCancel={() => {
        setDeleteModalOpen(false)
        setDeletingJob(null)
      }}
      onOk={() => {
        const job = deletingJob
        setDeleteModalOpen(false)
        setDeletingJob(null)
        if (job) {
          deleteJobRecord(job.job_id)
            .then(() => {
              message.success('已删除')
              refetch?.()
            })
            .catch((err: unknown) => {
              message.error(parseApiErrorMessage(err, '删除失败'))
            })
        }
      }}
      okText="确认删除"
      okType="danger"
      cancelText="取消"
      destroyOnClose
    >
      <p>确定要删除「<strong>{deletingJob?.name}</strong>」吗？仅删除数据库记录，磁盘数据保留。此操作不可撤销。</p>
    </Modal>
  </>
  )
}
