import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Col,
  Input,
  List,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
  Popconfirm,
} from 'antd'
import {
  BookOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  SendOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  knowledgeBaseApi,
  type ChatMessage,
  type KnowledgeDocument,
} from '../../shared/api/knowledge-base'
import { mergeCitationsByFilename } from '../utils/mergeCitations'

const { Title, Text, Paragraph } = Typography

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队中' },
  processing: { color: 'processing', label: '处理中' },
  ready: { color: 'success', label: '可用' },
  failed: { color: 'error', label: '失败' },
  archived: { color: 'default', label: '清洗归档' },
}

/** 仅直接上传、正在向量化的文档会触发自动刷新 */
function hasDirectUploadPending(docs: KnowledgeDocument[]): boolean {
  return docs.some(
    (d) => d.status !== 'archived' && (d.status === 'queued' || d.status === 'processing'),
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function KnowledgeBaseDetailPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [question, setQuestion] = useState('')
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)

  const { data: detail, isPending, isFetching, refetch } = useQuery({
    queryKey: ['knowledge-base', kbId],
    queryFn: () => knowledgeBaseApi.getBase(kbId!).then((r) => r.data),
    enabled: !!kbId,
    refetchInterval: (query) => {
      const docs = query.state.data?.documents || []
      return hasDirectUploadPending(docs) ? 3000 : false
    },
  })

  const { data: history = [] } = useQuery({
    queryKey: ['knowledge-base-messages', kbId],
    queryFn: () => knowledgeBaseApi.listMessages(kbId!).then((r) => r.data),
    enabled: !!kbId,
  })

  useEffect(() => {
    setLocalMessages(history)
  }, [history])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [localMessages])

  const uploadMutation = useMutation({
    mutationFn: (file: File) => knowledgeBaseApi.uploadDocument(kbId!, file).then((r) => r.data),
    onSuccess: () => {
      message.success('文档已上传，正在处理')
      queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '上传失败')
    },
  })

  const deleteDocMutation = useMutation({
    mutationFn: (docId: string) => knowledgeBaseApi.deleteDocument(kbId!, docId),
    onSuccess: () => {
      message.success('文档已删除')
      queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '删除失败')
    },
  })

  const chatMutation = useMutation({
    mutationFn: (q: string) => knowledgeBaseApi.chat(kbId!, q).then((r) => r.data),
    onSuccess: (res) => {
      const assistantMsg: ChatMessage = {
        id: res.message_id,
        role: 'assistant',
        content: res.answer,
        citations: res.citations,
        created_at: new Date().toISOString(),
      }
      setLocalMessages((prev) => [...prev, assistantMsg])
      queryClient.invalidateQueries({ queryKey: ['knowledge-base-messages', kbId] })
      setQuestion('')
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '问答失败')
    },
  })

  const handleSend = () => {
    const q = question.trim()
    if (!q) return
    const userMsg: ChatMessage = {
      id: `local-${Date.now()}`,
      role: 'user',
      content: q,
      citations: [],
      created_at: new Date().toISOString(),
    }
    setLocalMessages((prev) => [...prev, userMsg])
    chatMutation.mutate(q)
  }

  const renderDoc = (doc: KnowledgeDocument) => {
    const st = STATUS_MAP[doc.status] || { color: 'default', label: doc.status }
    return (
      <List.Item
        actions={
          doc.can_delete
            ? [
                <Popconfirm
                  key="del"
                  title="删除该文档？"
                  onConfirm={() => deleteDocMutation.mutate(doc.id)}
                >
                  <Button type="text" danger size="small" icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]
            : undefined
        }
      >
        <List.Item.Meta
          title={
            <Space>
              <Text>{doc.filename}</Text>
              <Tag color={st.color}>{st.label}</Tag>
            </Space>
          }
          description={
            <Space direction="vertical" size={0}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                上传：{doc.username || '—'}
                {' · '}
                {formatSize(doc.file_size)}
                {doc.chunk_count > 0 ? ` · ${doc.chunk_count} 块` : ''}
                {doc.asset_count > 0 ? ` · ${doc.asset_count} 图` : ''}
              </Text>
              {doc.error && (
                <Text type="danger" style={{ fontSize: 12 }}>
                  {doc.error}
                </Text>
              )}
            </Space>
          }
        />
      </List.Item>
    )
  }

  if (isPending && !detail) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin />
      </div>
    )
  }

  if (!detail) {
    return null
  }

  const hasReady =
    detail.ready_document_count > 0 || (detail.vector_chunk_count ?? 0) > 0
  const hasArchivedClean = (detail.archived_document_count ?? 0) > 0
  const hasArchivedOnly =
    !hasReady && hasArchivedClean && detail.document_count === 0

  return (
    <div style={{ padding: 24, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          {
            title: (
              <span style={{ cursor: 'pointer' }} onClick={() => navigate('/knowledge-base')}>
                知识库
              </span>
            ),
          },
          { title: detail.name },
        ]}
      />

      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <BookOutlined style={{ marginRight: 8 }} />
          {detail.name}
        </Title>
        {detail.description && (
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {detail.description}
          </Paragraph>
        )}
      </div>

      {!hasReady && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={
            hasArchivedOnly
              ? '知识库尚无可检索内容'
              : '请先上传文档并等待处理完成'
          }
          description={
            hasArchivedOnly
              ? '当前仅有数据清洗归档的原始文件，未写入向量库。请打开「数据清洗」完成审核并「批准入库」，或在下方直接上传文档并等待状态变为「可用」。'
              : '支持 md、txt、doc、docx、pdf、pptx、xlsx。含图片/流程图的文档将使用本地 Qwen2.5-VL 识别后入库。'
          }
        />
      )}

      <Row gutter={16} style={{ flex: 1, minHeight: 0 }}>
        <Col xs={24} lg={10} style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <Card
            title="文档"
            extra={
              <Space>
                <Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()}>
                  刷新
                </Button>
                <Upload
                  showUploadList={false}
                  accept=".md,.markdown,.txt,.doc,.docx,.pdf,.pptx,.xlsx"
                  beforeUpload={(file) => {
                    uploadMutation.mutate(file)
                    return false
                  }}
                >
                  <Button
                    type="primary"
                    size="small"
                    icon={<CloudUploadOutlined />}
                    loading={uploadMutation.isPending}
                  >
                    上传
                  </Button>
                </Upload>
              </Space>
            }
            style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
            styles={{ body: { flex: 1, overflow: 'auto', padding: 0 } }}
          >
            <List
              dataSource={detail.documents}
              locale={{ emptyText: '暂无文档，请上传' }}
              renderItem={renderDoc}
              style={{ padding: '0 16px' }}
              loading={isFetching && hasDirectUploadPending(detail.documents)}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14} style={{ display: 'flex', flexDirection: 'column', minHeight: 0, marginTop: 16 }}>
          <Card
            title="知识库对话"
            style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
            styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 } }}
          >
            <div style={{ flex: 1, overflow: 'auto', marginBottom: 16, paddingRight: 8 }}>
              {localMessages.length === 0 ? (
                <Text type="secondary">向知识库提问，将基于已入库文档 RAG 检索后回答</Text>
              ) : (
                localMessages.map((msg) => (
                  <div
                    key={msg.id}
                    style={{
                      marginBottom: 16,
                      textAlign: msg.role === 'user' ? 'right' : 'left',
                    }}
                  >
                    <div
                      style={{
                        display: 'inline-block',
                        maxWidth: '90%',
                        padding: '10px 14px',
                        borderRadius: 12,
                        background:
                          msg.role === 'user'
                            ? 'color-mix(in srgb, var(--color-primary) 12%, transparent)'
                            : 'var(--color-bg-secondary)',
                        textAlign: 'left',
                      }}
                    >
                      <Paragraph style={{ marginBottom: msg.citations?.length ? 8 : 0, whiteSpace: 'pre-wrap' }}>
                        {msg.content}
                      </Paragraph>
                      {msg.citations && msg.citations.length > 0 && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            参考来源：
                          </Text>
                          {mergeCitationsByFilename(msg.citations).map((c) => (
                            <Tag key={c.key} style={{ marginTop: 4 }}>
                              {c.label}
                            </Tag>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={chatEndRef} />
            </div>

            <Space.Compact style={{ width: '100%' }}>
              <Input.TextArea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={hasReady ? '输入问题…' : '暂无可检索内容，请先批准清洗入库或直接上传文档'}
                autoSize={{ minRows: 1, maxRows: 4 }}
                disabled={!hasReady || chatMutation.isPending}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                loading={chatMutation.isPending}
                disabled={!hasReady}
              >
                发送
              </Button>
            </Space.Compact>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
