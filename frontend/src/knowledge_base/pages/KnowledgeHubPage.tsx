import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import { BookOutlined, FilterOutlined, SendOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  knowledgeBaseApi,
  type ChatMessage,
} from '../../shared/api/knowledge-base'
import CleanJobListPage from '../../data_cleaning/pages/CleanJobListPage'
import { mergeCitationsByFilename } from '../utils/mergeCitations'
import './KnowledgeHubPage.css'

const { Title, Text, Paragraph } = Typography

/** 知识问答面板：仅 RAG 对话，文档经「清洗入库」Tab 写入 */
function KnowledgeChatPanel({ kbId }: { kbId: string }) {
  const queryClient = useQueryClient()
  const [question, setQuestion] = useState('')
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)

  const { data: detail } = useQuery({
    queryKey: ['knowledge-base', kbId],
    queryFn: () => knowledgeBaseApi.getBase(kbId).then((r) => r.data),
    enabled: !!kbId,
  })

  const { data: history = [] } = useQuery({
    queryKey: ['knowledge-base-messages', kbId],
    queryFn: () => knowledgeBaseApi.listMessages(kbId).then((r) => r.data),
    enabled: !!kbId,
  })

  useEffect(() => {
    setLocalMessages(history)
  }, [history])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [localMessages])

  const chatMutation = useMutation({
    mutationFn: (q: string) => knowledgeBaseApi.chat(kbId, q).then((r) => r.data),
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

  const hasReady =
    (detail?.ready_document_count ?? 0) > 0 || (detail?.vector_chunk_count ?? 0) > 0
  const hasArchivedOnly =
    !hasReady &&
    (detail?.archived_document_count ?? 0) > 0 &&
    (detail?.document_count ?? 0) === 0

  return (
    <div className="knowledge-hub-chat">
      {!hasReady && (
        <Alert
          className="knowledge-hub-chat__alert"
          type="info"
          showIcon
          message={hasArchivedOnly ? '尚无可检索内容' : '知识库为空'}
          description={
            hasArchivedOnly
              ? '已有清洗任务待审核。请切换到「清洗入库」完成审核并批准入库后即可提问。'
              : '请切换到「清洗入库」上传文档，经审核批准后即可在此提问。'
          }
        />
      )}

      <Card title="知识问答" className="knowledge-hub-chat__card">
        <div className="knowledge-hub-chat__messages">
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
                        ? 'rgba(0, 112, 243, 0.12)'
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

        <Space.Compact className="knowledge-hub-chat__input" style={{ width: '100%' }}>
          <Input.TextArea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={hasReady ? '输入问题…' : '请先完成清洗入库后再提问'}
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
    </div>
  )
}

/**
 * 全站唯一知识库入口：问答 + 清洗入库 两个 Tab。
 * 布局：标题与 Tab 栏固定，各 Tab 内容在内部滚动。
 */
export default function KnowledgeHubPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') === 'clean' ? 'clean' : 'chat'

  const { data: kbase, isPending } = useQuery({
    queryKey: ['knowledge-base-default'],
    queryFn: () => knowledgeBaseApi.getDefaultBase().then((r) => r.data),
  })

  if (isPending || !kbase) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin />
      </div>
    )
  }

  return (
    <div className="knowledge-hub-page">
      <div className="knowledge-hub-page__header">
        <Title level={3} style={{ margin: 0 }}>
          <BookOutlined style={{ color: 'var(--color-primary)', marginRight: 8 }} />
          知识库
        </Title>
        <Text type="secondary">
          上传文档经清洗审核入库后，在此进行 RAG 问答（全站共用一个知识库）
        </Text>
      </div>

      <Tabs
        className="knowledge-hub-page__tabs"
        activeKey={activeTab}
        onChange={(key) => setSearchParams(key === 'chat' ? {} : { tab: key })}
        items={[
          {
            key: 'chat',
            label: '知识问答',
            children: <KnowledgeChatPanel kbId={kbase.id} />,
          },
          {
            key: 'clean',
            label: (
              <span>
                <FilterOutlined style={{ marginRight: 6 }} />
                清洗入库
              </span>
            ),
            children: (
              <div className="knowledge-hub-clean">
                <CleanJobListPage embedded kbId={kbase.id} reviewPathPrefix="/knowledge-base/clean" />
              </div>
            ),
          },
        ]}
      />

      <Text type="secondary" className="knowledge-hub-page__footer">
        designed by @huangjing
      </Text>
    </div>
  )
}
