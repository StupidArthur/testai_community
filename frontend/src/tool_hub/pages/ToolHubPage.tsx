import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  PlusOutlined,
  ToolOutlined,
  CloudDownloadOutlined,
  LinkOutlined,
  DesktopOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toolHubApi, type ToolCard, type ToolKind } from '../../shared/api/tool-hub'

const { Title, Text } = Typography
const { TextArea } = Input

const KIND_LABEL: Record<ToolKind, string> = {
  client: '客户端工具',
  platform: '平台集成',
}

function ToolKindTag({ kind }: { kind: ToolKind }) {
  return (
    <Tag color={kind === 'client' ? 'blue' : 'purple'} icon={kind === 'client' ? <DesktopOutlined /> : <AppstoreOutlined />}>
      {KIND_LABEL[kind]}
    </Tag>
  )
}

export default function ToolHubPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [kindFilter, setKindFilter] = useState<ToolKind | 'all'>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [artifactFile, setArtifactFile] = useState<File | null>(null)
  const createKind = Form.useWatch('tool_kind', createForm) as ToolKind | undefined

  const { data: tools = [], isLoading } = useQuery({
    queryKey: ['tool-hub', kindFilter],
    queryFn: () =>
      toolHubApi
        .list(kindFilter === 'all' ? undefined : { tool_kind: kindFilter })
        .then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: toolHubApi.create,
    onSuccess: () => {
      message.success('工具已发布')
      setCreateOpen(false)
      createForm.resetFields()
      setArtifactFile(null)
      queryClient.invalidateQueries({ queryKey: ['tool-hub'] })
    },
    onError: (err: Error) => message.error(err.message || '发布失败'),
  })

  const filtered = useMemo(() => tools, [tools])

  const openTool = (tool: ToolCard) => {
    navigate(`/tool-hub/${tool.id}`)
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <Title level={3} style={{ margin: 0, color: 'var(--color-text)' }}>
            <ToolOutlined style={{ marginRight: 8, color: 'var(--color-primary)' }} />
            工具集
          </Title>
          <Text type="secondary">客户端可下载工具与平台集成工具</Text>
        </div>
        <Space>
          <Select
            value={kindFilter}
            onChange={setKindFilter}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '全部类型' },
              { value: 'client', label: '客户端工具' },
              { value: 'platform', label: '平台集成' },
            ]}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            上传工具
          </Button>
        </Space>
      </div>

      {isLoading ? (
        <Card loading />
      ) : filtered.length === 0 ? (
        <Empty description="暂无工具，点击右上角上传" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((tool) => (
            <Col key={tool.id} xs={24} sm={12} md={8}>
              <Card
                hoverable
                onClick={() => openTool(tool)}
                style={{
                  border: '1px solid var(--color-border)',
                  opacity: tool.enabled ? 1 : 0.65,
                }}
              >
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <Title level={5} style={{ margin: 0 }}>{tool.display_name}</Title>
                    <ToolKindTag kind={tool.tool_kind} />
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {tool.slug} · v{tool.latest_version || '-'} · {tool.owner_username}
                  </Text>
                  {!tool.enabled && <Tag color="default">已下架</Tag>}
                  <Text style={{ color: 'var(--color-primary)' }}>进入 →</Text>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Modal
        title="上传工具"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false)
          createForm.resetFields()
          setArtifactFile(null)
        }}
        footer={null}
        width={640}
        destroyOnHidden
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{ tool_kind: 'client', tool_type: 'default', version_label: '1.0.0' }}
          onFinish={(values) => {
            if (values.tool_kind === 'client' && !artifactFile) {
              message.error('客户端工具须上传可执行文件')
              return
            }
            createMutation.mutate({
              slug: values.slug,
              display_name: values.display_name,
              tool_kind: values.tool_kind,
              tool_type: values.tool_type,
              link_url: values.link_url,
              version_label: values.version_label,
              manual_md: values.manual_md,
              artifact: artifactFile,
            })
          }}
        >
          <Form.Item name="display_name" label="工具名称" rules={[{ required: true }]}>
            <Input placeholder="展示名称" />
          </Form.Item>
          <Form.Item
            name="slug"
            label="工具标识"
            rules={[{ required: true, message: '请输入唯一标识' }]}
            extra="小写字母开头，仅含 a-z、0-9、_"
          >
            <Input placeholder="如 my_client_tool" />
          </Form.Item>
          <Form.Item name="tool_kind" label="工具类型" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value="client">客户端工具（可下载 exe）</Radio>
              <Radio value="platform">平台集成工具</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="tool_type" label="tool_type（预留）">
            <Input placeholder="default" />
          </Form.Item>
          {createKind === 'platform' && (
            <Form.Item
              name="link_url"
              label="跳转链接"
              rules={[{ required: true, message: '请填写跳转地址' }]}
              extra="站内路径如 /translate，或完整外链 https://..."
            >
              <Input prefix={<LinkOutlined />} placeholder="/translate" />
            </Form.Item>
          )}
          <Form.Item name="version_label" label="初始版本号">
            <Input placeholder="1.0.0" />
          </Form.Item>
          {createKind === 'client' && (
            <Form.Item label="工具文件" required>
              <Upload
                maxCount={1}
                beforeUpload={(file) => {
                  setArtifactFile(file)
                  return false
                }}
                onRemove={() => setArtifactFile(null)}
                accept=".exe,.zip,.msi"
              >
                <Button icon={<CloudDownloadOutlined />}>选择 exe / zip / msi</Button>
              </Upload>
            </Form.Item>
          )}
          <Form.Item
            name="manual_md"
            label="使用说明（Markdown）"
            rules={[{ required: true, message: '请填写使用说明' }]}
          >
            <TextArea rows={8} placeholder="# 工具说明&#10;&#10;## 安装&#10;..." />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={createMutation.isPending}>
              发布
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Text type="secondary" style={{ marginTop: 24, textAlign: 'center', fontSize: 12 }}>
        designed by @yuzechao
      </Text>
    </div>
  )
}
