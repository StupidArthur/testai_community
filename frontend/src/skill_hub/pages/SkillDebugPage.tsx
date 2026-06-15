import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Input,
  Typography,
  Select,
  Space,
  Tag,
  Spin,
  Alert,
  Breadcrumb,
  message,
} from 'antd'
import {
  BugOutlined,
  PlayCircleOutlined,
  DatabaseOutlined,
  ApartmentOutlined,
  BranchesOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import type { Branch, SkillVersion } from '../../shared/api/client'

const { Title, Text } = Typography

function branchLabel(b: Branch): string {
  if (b.branch_type === 'master') return 'Master（主干）'
  if (b.branch_type === 'standard') return `Standard（${b.username}）`
  return `Personal（${b.username}）`
}

export default function SkillDebugPage() {
  const { skillId } = useParams<{ skillId: string }>()
  const navigate = useNavigate()

  const [branchId, setBranchId] = useState<number | null>(null)
  const [versionId, setVersionId] = useState<string | null>(null)
  const [userInput, setUserInput] = useState('')
  const [output, setOutput] = useState('')

  const { data: skill } = useQuery({
    queryKey: ['skill', skillId],
    queryFn: () => skillsApi.get(skillId!).then((r) => r.data),
    enabled: !!skillId,
  })

  const { data: branches = [] } = useQuery({
    queryKey: ['branches', skillId],
    queryFn: () => skillsApi.listBranches(skillId!).then((r) => r.data),
    enabled: !!skillId,
  })

  const sortedBranches = useMemo(() => {
    const pin: Record<string, number> = { master: 0, standard: 1, personal: 2 }
    return [...branches].sort(
      (a, b) => (pin[a.branch_type] ?? 99) - (pin[b.branch_type] ?? 99),
    )
  }, [branches])

  useEffect(() => {
    if (sortedBranches.length > 0 && branchId === null) {
      const master = sortedBranches.find((b) => b.branch_type === 'master')
      setBranchId((master ?? sortedBranches[0]).id)
    }
  }, [sortedBranches, branchId])

  const { data: versions = [], isLoading: versionsLoading } = useQuery<SkillVersion[]>({
    queryKey: ['versions', skillId, branchId],
    queryFn: () => skillsApi.getVersions(skillId!, branchId!).then((r) => r.data),
    enabled: !!skillId && branchId !== null,
  })

  useEffect(() => {
    if (versions.length > 0) {
      setVersionId(versions[0].id)
    } else {
      setVersionId(null)
    }
  }, [versions])

  const selectedVersion = useMemo(
    () => versions.find((v) => v.id === versionId) ?? null,
    [versions, versionId],
  )

  const { data: resolved, isLoading: payloadLoading } = useQuery({
    queryKey: ['skill-debug-payload', skillId, versionId],
    queryFn: () =>
      skillsApi
        .resolve({
          resolve_mode: 'pinned',
          skill_name: skill?.name,
          version_id: versionId!,
        })
        .then((r) => r.data),
    enabled: !!skill?.name && !!versionId,
  })

  const runMutation = useMutation({
    mutationFn: () =>
      skillsApi.debugRun(skillId!, {
        user_input: userInput,
        version_id: versionId ?? undefined,
        branch_id: versionId ? undefined : branchId ?? undefined,
      }),
    onSuccess: (res) => {
      setOutput(res.data.output)
      message.success('执行完成')
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '执行失败')
    },
  })

  const handleRun = () => {
    if (!userInput.trim()) {
      message.warning('请输入调试内容')
      return
    }
    if (!versionId && branchId === null) {
      message.warning('请选择分支与版本')
      return
    }
    runMutation.mutate()
  }

  const payloadText = resolved?.payload ?? ''

  return (
    <div style={{ height: 'calc(100vh - 64px - 48px)', display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          padding: '12px 0 16px',
          borderBottom: '1px solid var(--color-border)',
          marginBottom: 16,
        }}
      >
        <Breadcrumb
          items={[
            {
              title: (
                <span onClick={() => navigate('/skills')} style={{ cursor: 'pointer', color: 'var(--color-primary)' }}>
                  <DatabaseOutlined style={{ marginRight: 4 }} />
                  Skill 仓库
                </span>
              ),
            },
            {
              title: (
                <span
                  onClick={() => navigate(`/skill/${skillId}`)}
                  style={{ cursor: 'pointer', color: 'var(--color-primary)' }}
                >
                  <ApartmentOutlined style={{ marginRight: 4 }} />
                  {skill?.display_name || '...'}
                </span>
              ),
            },
            {
              title: (
                <span>
                  <BugOutlined style={{ marginRight: 4 }} />
                  Skill 调试
                </span>
              ),
            },
          ]}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
          <Title level={4} style={{ margin: 0, color: 'var(--color-text)' }}>
            <BugOutlined style={{ marginRight: 8, color: 'var(--color-primary)' }} />
            Skill 调试沙箱
          </Title>
          <Space>
            <Select
              style={{ width: 200 }}
              placeholder="选择分支"
              value={branchId ?? undefined}
              onChange={(v) => setBranchId(v)}
              options={sortedBranches.map((b) => ({ value: b.id, label: branchLabel(b) }))}
            />
            <Select
              style={{ width: 160 }}
              placeholder="选择版本"
              value={versionId ?? undefined}
              onChange={setVersionId}
              loading={versionsLoading}
              options={versions.map((v) => ({
                value: v.id,
                label: `v${v.version_num}${v.id === versions[0]?.id ? ' · HEAD' : ''}`,
              }))}
              disabled={versions.length === 0}
            />
            {selectedVersion && (
              <Tag color="cyan">rev {selectedVersion.revision}</Tag>
            )}
          </Space>
        </div>
      </div>

      {versions.length === 0 && !versionsLoading ? (
        <Alert type="warning" showIcon message="当前分支暂无版本，请先在沙盒中提交版本后再调试" />
      ) : (
        <div style={{ flex: 1, display: 'flex', gap: 16, minHeight: 0 }}>
          {/* 左侧：Skill Prompt */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              border: '1px solid var(--color-border)',
              borderRadius: 8,
              background: 'var(--color-bg)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '10px 16px',
                borderBottom: '1px solid var(--color-border)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <CodeOutlined style={{ color: 'var(--color-primary)' }} />
              <Text strong>Skill 内容（System Prompt）</Text>
              {resolved?.version_locator && (
                <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
                  {resolved.version_locator}
                </Text>
              )}
            </div>
            <div style={{ flex: 1, padding: 12, overflow: 'auto' }}>
              {payloadLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin />
                </div>
              ) : (
                <Input.TextArea
                  value={payloadText}
                  readOnly
                  autoSize={false}
                  style={{
                    height: '100%',
                    minHeight: 360,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    lineHeight: 1.6,
                    resize: 'none',
                    border: 'none',
                    background: 'var(--color-bg-secondary)',
                  }}
                />
              )}
            </div>
          </div>

          {/* 右侧：调试输入与输出 */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              border: '1px solid var(--color-border)',
              borderRadius: 8,
              background: 'var(--color-bg)',
              overflow: 'hidden',
            }}
          >
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <Text strong>
                <PlayCircleOutlined style={{ marginRight: 6, color: 'var(--color-primary)' }} />
                调试执行
              </Text>
            </div>
            <div style={{ padding: 12, flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                  用户输入（User Message）
                </Text>
                <Input.TextArea
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  placeholder="输入要发送给该 Skill 的内容，例如测试问题、样例数据、任务描述…"
                  autoSize={{ minRows: 6, maxRows: 10 }}
                  maxLength={16000}
                  showCount
                />
              </div>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                size="large"
                loading={runMutation.isPending}
                onClick={handleRun}
                disabled={!versionId}
              >
                {runMutation.isPending ? '执行中（约 5–30 秒）…' : '运行 Skill'}
              </Button>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                <Text type="secondary" style={{ fontSize: 12, marginBottom: 6 }}>
                  模型输出（Assistant）
                </Text>
                <Input.TextArea
                  value={output}
                  readOnly
                  placeholder="运行后在此显示 Skill 输出…"
                  style={{
                    flex: 1,
                    minHeight: 200,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    lineHeight: 1.6,
                    background: 'var(--color-bg-secondary)',
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      <Text type="secondary" style={{ textAlign: 'right', fontSize: 11, marginTop: 8 }}>
        designed by @yuzechao
      </Text>
    </div>
  )
}
