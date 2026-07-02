import { useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  CloudDownloadOutlined,
  LinkOutlined,
  EditOutlined,
  PlusOutlined,
  StopOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  downloadToolArtifact,
  toolHubApi,
} from '../../shared/api/tool-hub'
import ToolMarkdownPanel from '../components/ToolMarkdownPanel'
import { artifactRequiredRules, artifactUploadFieldProps, extractUploadFile, type ArtifactFileList } from '../utils/uploadForm'

const { Title, Text } = Typography
const { TextArea } = Input

interface VersionFormValues {
  version_label: string
  changelog_md: string
  artifact?: ArtifactFileList
}

export default function ToolDetailPage() {
  const { toolId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [versionOpen, setVersionOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [versionForm] = Form.useForm<VersionFormValues>()
  const [editForm] = Form.useForm()

  const { data: tool, isLoading } = useQuery({
    queryKey: ['tool-hub', toolId],
    queryFn: () => toolHubApi.get(toolId).then((r) => r.data),
    enabled: !!toolId,
  })

  const versionMutation = useMutation({
    mutationFn: (values: VersionFormValues) =>
      toolHubApi.addVersion(toolId, {
        version_label: values.version_label,
        changelog_md: values.changelog_md,
        artifact: extractUploadFile(values.artifact),
      }),
    onSuccess: () => {
      message.success('新版本已发布')
      setVersionOpen(false)
      versionForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['tool-hub'] })
    },
    onError: (err: Error) => message.error(err.message || '发布失败'),
  })

  const updateMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => toolHubApi.update(toolId, values),
    onSuccess: () => {
      message.success('已保存')
      setEditOpen(false)
      queryClient.invalidateQueries({ queryKey: ['tool-hub'] })
    },
    onError: (err: Error) => message.error(err.message || '保存失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => toolHubApi.delete(toolId),
    onSuccess: () => {
      message.success('工具已删除')
      navigate('/tool-hub')
    },
    onError: (err: Error) => message.error(err.message || '删除失败'),
  })

  const handlePrimaryAction = async () => {
    if (!tool) return
    if (tool.tool_kind === 'client') {
      try {
        const latest = tool.versions[0]
        await downloadToolArtifact(
          tool.id,
          latest?.artifact_filename || (tool.slug === 'feature_recorder' ? 'feature-recorder-win64.zip' : `${tool.slug}.exe`),
        )
      } catch (err: unknown) {
        message.error(err instanceof Error ? err.message : '下载失败')
      }
      return
    }
    if (!tool.link_url) {
      message.warning('未配置跳转链接')
      return
    }
    if (tool.link_url.startsWith('http://') || tool.link_url.startsWith('https://')) {
      window.open(tool.link_url, '_blank')
    } else {
      navigate(tool.link_url)
    }
  }

  if (isLoading || !tool) {
    return <Card loading style={{ maxWidth: 960, margin: '0 auto' }} />
  }

  return (
    <div
      style={{
        maxWidth: 960,
        margin: '0 auto',
        height: 'calc(100vh - 64px - 48px)',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      <Button type="link" onClick={() => navigate('/tool-hub')} style={{ paddingLeft: 0, alignSelf: 'flex-start', flexShrink: 0 }}>
        ← 返回工具集
      </Button>

      {tool.slug === 'feature_recorder' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12, flexShrink: 0 }}
          message="录制完成后，将 output/run_* 目录打成 zip，在「AI 翻译」中上传生成用例。"
          action={
            <Button size="small" type="primary" onClick={() => navigate('/translate')}>
              去 AI 翻译
            </Button>
          }
        />
      )}
      {tool.slug === 'ai_translate' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12, flexShrink: 0 }}
          message="请先在工具集下载「功能录制」客户端，录制并打包 zip 后再回到本页上传。"
          action={
            <Button size="small" onClick={() => navigate('/tool-hub')}>
              打开工具集
            </Button>
          }
        />
      )}

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 12,
          flexShrink: 0,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0 }}>
            {tool.display_name}
            {!tool.enabled && <Tag style={{ marginLeft: 8 }}>已下架</Tag>}
          </Title>
          <Text type="secondary">
            {tool.slug} · v{tool.latest_version || '-'} · {tool.owner_username} · tool_type={tool.tool_type}
          </Text>
        </div>
        <Space wrap>
          {tool.can_edit && (
            <>
              <Button icon={<EditOutlined />} onClick={() => {
                const latestManual = tool.versions[0]?.manual_md ?? ''
                editForm.setFieldsValue({
                  display_name: tool.display_name,
                  link_url: tool.link_url,
                  tool_type: tool.tool_type,
                  manual_md: latestManual,
                })
                setEditOpen(true)
              }}>
                编辑
              </Button>
              <Button icon={<PlusOutlined />} onClick={() => setVersionOpen(true)}>
                新版本
              </Button>
              <Button
                icon={<StopOutlined />}
                onClick={() => updateMutation.mutate({ enabled: !tool.enabled })}
                loading={updateMutation.isPending}
              >
                {tool.enabled ? '下架' : '上架'}
              </Button>
            </>
          )}
          {tool.can_delete && (
            <Popconfirm title="确定删除此工具？" onConfirm={() => deleteMutation.mutate()}>
              <Button danger icon={<DeleteOutlined />} loading={deleteMutation.isPending}>
                删除
              </Button>
            </Popconfirm>
          )}
          <Button
            type="primary"
            size="large"
            icon={tool.tool_kind === 'client' ? <CloudDownloadOutlined /> : <LinkOutlined />}
            onClick={handlePrimaryAction}
            disabled={tool.tool_kind === 'client' && !tool.has_artifact}
          >
            {tool.tool_kind === 'client' ? '下载' : '进入工具'}
          </Button>
        </Space>
      </div>

      <ToolMarkdownPanel markdown={tool.combined_markdown} />

      <Modal
        title="发布新版本"
        open={versionOpen}
        onCancel={() => {
          setVersionOpen(false)
          versionForm.resetFields()
          versionMutation.reset()
        }}
        footer={null}
        destroyOnHidden
      >
        <Form
          form={versionForm}
          layout="vertical"
          initialValues={{ artifact: [] }}
          onFinish={(values) => versionMutation.mutate(values)}
          onFinishFailed={() => {
            if (tool.tool_kind === 'client') {
              message.warning('请完善表单信息，客户端工具须选择新版本文件')
            }
          }}
        >
          <Form.Item
            name="version_label"
            label="版本号"
            rules={[
              { required: true, message: '请输入版本号' },
              { max: 32, message: '最多 32 个字符' },
            ]}
          >
            <Input placeholder="2.0.0" />
          </Form.Item>
          {tool.tool_kind === 'client' && (
            <Form.Item
              name="artifact"
              label="新版本文件"
              required
              rules={artifactRequiredRules}
              extra="客户端工具发布新版本必须上传 exe / zip / msi 文件"
              {...artifactUploadFieldProps}
            >
              <Upload maxCount={1} beforeUpload={() => false} accept=".exe,.zip,.msi">
                <Button icon={<CloudDownloadOutlined />}>选择文件</Button>
              </Upload>
            </Form.Item>
          )}
          <Form.Item
            name="changelog_md"
            label="更新日志（Markdown）"
            rules={[{ required: true, message: '请填写 changelog' }]}
          >
            <TextArea rows={6} placeholder="## 2.0.0&#10;&#10;- 修复问题" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={versionMutation.isPending}>
              提交
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑工具"
        open={editOpen}
        onCancel={() => {
          setEditOpen(false)
          updateMutation.reset()
        }}
        footer={null}
        width={720}
        destroyOnHidden
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={(values) => updateMutation.mutate(values)}
        >
          <Form.Item
            name="display_name"
            label="工具名称"
            rules={[
              { required: true, message: '请输入工具名称' },
              { max: 128, message: '最多 128 个字符' },
            ]}
          >
            <Input />
          </Form.Item>
          {tool.tool_kind === 'platform' && (
            <Form.Item name="link_url" label="跳转链接" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          )}
          <Form.Item name="tool_type" label="tool_type">
            <Input />
          </Form.Item>
          <Form.Item
            name="manual_md"
            label="使用说明（Markdown）"
            rules={[{ required: true, message: '请填写使用说明' }]}
            extra="修改后将更新当前最新版本的使用说明，无需发布新版本"
          >
            <TextArea rows={12} placeholder="# 工具说明&#10;&#10;## 安装&#10;..." />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={updateMutation.isPending}>
              保存
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
