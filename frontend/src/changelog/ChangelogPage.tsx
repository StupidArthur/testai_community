import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Typography,
  List,
  Button,
  Modal,
  Form,
  Input,
  message,
  Popconfirm,
  Tag,
  Space,
  Empty,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import {
  listChangelog,
  createChangelog,
  updateChangelog,
  deleteChangelog,
  type ChangelogView,
  type ChangelogCreate,
} from '../shared/api/changelog'

const { Title, Text } = Typography
const { TextArea } = Input

const VERSION_REGEX = /^\d+\.\d+\.\d+$/

export default function ChangelogPage() {
  const [entries, setEntries] = useState<ChangelogView[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ChangelogView | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const isAdmin = user.role === 'Admin'

  const fetchEntries = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listChangelog()
      setEntries(data)
    } catch {
      message.error('加载更新日志失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchEntries()
  }, [fetchEntries])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (entry: ChangelogView) => {
    setEditing(entry)
    form.setFieldsValue({
      version: entry.version,
      title: entry.title,
      content: entry.content,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (!VERSION_REGEX.test(values.version)) {
        message.error('版本号格式应为 x.y.z，如 3.2.0')
        return
      }
      setSubmitting(true)
      if (editing) {
        await updateChangelog(editing.id, values)
        message.success('更新成功')
      } else {
        await createChangelog(values as ChangelogCreate)
        message.success('发布成功')
      }
      setModalOpen(false)
      fetchEntries()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (detail) {
        message.error(detail)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteChangelog(id)
      message.success('已删除')
      fetchEntries()
    } catch {
      message.error('删除失败')
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <HistoryOutlined style={{ fontSize: 28, color: 'var(--color-primary)' }} />
          <Title level={3} style={{ margin: 0, color: 'var(--color-text)' }}>更新日志</Title>
        </div>
        {isAdmin && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            发布更新
          </Button>
        )}
      </div>

      <List
        loading={loading}
        dataSource={entries}
        locale={{ emptyText: <Empty description="暂无更新记录" /> }}
        renderItem={(entry) => (
          <Card
            key={entry.id}
            style={{
              marginBottom: 16,
              border: '1px solid var(--color-border)',
              background: 'var(--color-bg)',
            }}
            bodyStyle={{ padding: '20px 24px' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <Tag color="blue" style={{ fontSize: 14, padding: '2px 10px', margin: 0 }}>
                  v{entry.version}
                </Tag>
                <Text strong style={{ fontSize: 16, color: 'var(--color-text)' }}>{entry.title}</Text>
              </div>
              <Space size={4}>
                {isAdmin && (
                  <>
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => openEdit(entry)}
                    />
                    <Popconfirm
                      title="确认删除此更新记录？"
                      onConfirm={() => handleDelete(entry.id)}
                      okText="删除"
                      cancelText="取消"
                    >
                      <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </>
                )}
              </Space>
            </div>

            {entry.content && (
              <div
                style={{
                  color: 'var(--color-text-secondary)',
                  lineHeight: 1.8,
                  fontSize: 14,
                }}
                className="changelog-content"
              >
                <ReactMarkdown>{entry.content}</ReactMarkdown>
              </div>
            )}

            <div style={{ marginTop: 12, display: 'flex', gap: 16, color: 'var(--color-text-tertiary)', fontSize: 12 }}>
              {entry.published_by && <span>发布人：{entry.published_by}</span>}
              <span>{entry.created_at.slice(0, 10)}</span>
            </div>
          </Card>
        )}
      />

      <Modal
        title={editing ? '编辑更新' : '发布版本更新'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText={editing ? '保存' : '发布'}
        cancelText="取消"
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="version"
            label="版本号"
            rules={[
              { required: true, message: '请输入版本号' },
              { pattern: VERSION_REGEX, message: '格式为 x.y.z，如 3.2.0' },
            ]}
          >
            <Input placeholder="如 3.2.0" />
          </Form.Item>
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="本次更新的简要标题" maxLength={200} />
          </Form.Item>
          <Form.Item name="content" label="更新内容（支持 Markdown）">
            <TextArea
              rows={12}
              placeholder={"## 🆕 新增功能\n- 功能A\n- 功能B\n\n## 🐛 问题修复\n- 修复了XXX\n\n## 🔧 优化\n- 优化了YYY"}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
