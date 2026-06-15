import { useState, useEffect, useMemo } from 'react'
import {
  Button,
  Input,
  message,
  Typography,
  Tag,
  Space,
  Spin,
  Alert,
  Modal,
  Radio,
  Breadcrumb,
} from 'antd'
import {
  BranchesOutlined,
  ForkOutlined,
  ProfileOutlined,
  CrownOutlined,
  HomeOutlined,
  ArrowUpOutlined,
  ClockCircleOutlined,
  EditOutlined,
  EyeOutlined,
  HistoryOutlined,
  ExperimentOutlined,
  RocketOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ApartmentOutlined,
} from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import { useCurrentUser, isAdmin as checkAdmin } from '../../shared/hooks/useAuth'
import type { Skill, Branch, SkillVersion, EvaluateDraftResponse } from '../../shared/api/client'

const { Title, Text } = Typography

const NINE_DIMS = [
  { key: 'role', label: 'Role（角色）', required: true, rows: 2,
    placeholder: '例：资深 API 自动化测试专家',
    guide: '用一句话定义这个 Agent 的核心身份；不要写目标/规则。' },
  { key: 'profile', label: 'Profile（配置档案）', rows: 4,
    placeholder: '例：\n- Author: QA Architect Team\n- Version: 2.0\n- Language: 中文\n- Description: ...',
    guide: 'Author / Version / Language / Description 四要素。' },
  { key: 'background', label: 'Background（背景说明）', rows: 4,
    placeholder: '描述 Agent 要解决的现实问题与场景上下文。',
    guide: '用 2-4 段说明业务背景，让 LLM 知道"为什么"。' },
  { key: 'goals', label: 'Goals（核心目标）', rows: 4,
    placeholder: '例：\n1. 解析 API 文档\n2. 提取关键字段\n3. 推演正常 + 异常路径\n4. 输出标准 Markdown',
    guide: '用有序列表说明 Agent 要达成的主要目标。' },
  { key: 'constraints', label: 'Constraints（约束与规则）', rows: 5,
    placeholder: '例：\n1. 必须大量使用强硬祈使句（如必须、严禁）设定红线。\n2. 必须包含安全测试。',
    guide: '必须大量使用强硬祈使句（如必须、严禁）设定红线。' },
  { key: 'core_skills', label: 'Core Skills（核心技能）', rows: 5,
    placeholder: '例：\n1. 解析 OpenAPI 3.0 / Swagger / YApi 三种格式…\n2. 对每个必填字段做等价类划分…',
    guide: '必须明确具体的实现逻辑，而不仅是名字。' },
  { key: 'workflows', label: 'Workflows（工作流）', rows: 5,
    placeholder: '例：\n1. 第一步：解析 API 文档\n2. 第二步：识别字段约束\n3. 第三步：推演正常路径\n4. 第四步：推演异常\n5. 第五步：输出 Markdown',
    guide: '必须是数字有序列表 (1, 2, 3...) 的闭环 SOP。' },
  { key: 'output_format', label: 'Output Format（输出格式）', rows: 5,
    placeholder: '请提供严格的 JSON 代码模板或 Markdown 排版结构。',
    guide: '请提供严格的 JSON 代码模板或 Markdown 排版结构。' },
  { key: 'initialization', label: 'Initialization（初始化/启动语）', rows: 3,
    placeholder: '例：作为资深 API 自动化测试专家，我已经准备好为您生成高覆盖率的测试用例。',
    guide: 'Agent 与用户对话的第一句话；告诉用户你能做什么 + 需要什么输入。' },
]

const EMPTY_9D = {
  role: '', profile: '', background: '', goals: '',
  constraints: '', core_skills: '', workflows: '',
  output_format: '', initialization: '',
}

type NineDimsKey = keyof typeof EMPTY_9D

function compileToRaw(form: typeof EMPTY_9D): string {
  return NINE_DIMS.map((d) => {
    const content = (form[d.key as NineDimsKey] || '').trim()
    return `### ${d.label}\n\n${content}`
  }).join('\n\n')
}

function parseToFormData(raw: string): { form: typeof EMPTY_9D; warnings: string[] } {
  const result = { ...EMPTY_9D }
  const warnings: string[] = []
  if (!raw || typeof raw !== 'string') return { form: result, warnings }

  // 构建 label → key 映射，支持英文名、中文名、常见别名
  const labelToKey: Record<string, NineDimsKey> = {}
  for (const d of NINE_DIMS) {
    const parts = d.label.split('（')
    const en = parts[0].trim()
    const zh = parts[1]?.replace('）', '').trim() || ''
    labelToKey[en.toLowerCase()] = d.key as NineDimsKey
    if (zh) labelToKey[zh] = d.key as NineDimsKey
  }
  // 常见别名
  const aliases: Record<string, NineDimsKey> = {
    '角色': 'role', '身份': 'role',
    '配置': 'profile', '档案': 'profile',
    '背景': 'background', '背景说明': 'background',
    '目标': 'goals', '核心目标': 'goals',
    '约束': 'constraints', '规则': 'constraints', '约束与规则': 'constraints',
    '技能': 'core_skills', '核心技能': 'core_skills',
    '工作流': 'workflows', '流程': 'workflows',
    '输出': 'output_format', '输出格式': 'output_format',
    '初始化': 'initialization', '启动语': 'initialization',
  }
  for (const [alias, key] of Object.entries(aliases)) {
    labelToKey[alias] = key
  }

  // 支持 # ## ### 三种标题级别
  const re = /^#{1,3} (.+?)\s*\n+([\s\S]*?)(?=^#{1,3} |$)/gm
  let m
  while ((m = re.exec(raw)) !== null) {
    const label = m[1].trim()
    const content = m[2].replace(/\s+$/, '').trim()
    if (!content) continue

    // 尝试匹配：先取括号前的英文名，再取中文名，再用完整标题
    const base = label.split('（')[0].trim()
    const key = labelToKey[base.toLowerCase()] || labelToKey[base] || labelToKey[label]
    if (key) {
      result[key] = content
    } else {
      const preview = content.length > 40 ? content.slice(0, 40) + '...' : content
      warnings.push(`「${label}」未匹配到已知维度，内容: ${preview}`)
    }
  }
  return { form: result, warnings }
}

function versionToForm(v: SkillVersion): typeof EMPTY_9D {
  if (!v) return { ...EMPTY_9D }
  return {
    role: v.role || '',
    profile: v.profile || '',
    background: v.background || '',
    goals: v.goals || '',
    constraints: v.constraints || '',
    core_skills: v.core_skills || '',
    workflows: v.workflows || '',
    output_format: v.output_format || '',
    initialization: v.initialization || '',
  }
}

export default function BranchSandbox() {
  const { skillId, branchId } = useParams<{ skillId: string; branchId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: skill } = useQuery<Skill>({
    queryKey: ['skill', skillId],
    queryFn: () => skillsApi.get(skillId!).then((r) => r.data),
    enabled: !!skillId,
  })

  const { data: branches = [] } = useQuery<Branch[]>({
    queryKey: ['branches', skillId],
    queryFn: () => skillsApi.listBranches(skillId!).then((r) => r.data),
    enabled: !!skillId,
  })

  const branch = useMemo(
    () => branches.find((x) => x.id === parseInt(branchId || '')) || null,
    [branches, branchId]
  )

  const { data: versions = [], isLoading: versionsLoading } = useQuery<SkillVersion[]>({
    queryKey: ['versions', skillId, branchId],
    queryFn: () => skillsApi.getVersions(skillId!, parseInt(branchId || '')).then((r) => r.data),
    enabled: !!skillId && !!branchId,
  })

  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const selectedVersion = useMemo(
    () => versions.find((v) => v.id === selectedVersionId) || null,
    [versions, selectedVersionId]
  )
  const isLatestVersion = useMemo(
    () => versions.length > 0 && selectedVersionId === versions[0]?.id,
    [versions, selectedVersionId]
  )

  const [form, setForm] = useState<typeof EMPTY_9D>(EMPTY_9D)
  const [rawText, setRawText] = useState('')
  const [editMode, setEditMode] = useState<'structured' | 'raw'>('structured')

  const [isCommitModalVisible, setIsCommitModalVisible] = useState(false)
  const [isEvaluating, setIsEvaluating] = useState(false)
  const [evaluationResult, setEvaluationResult] = useState<EvaluateDraftResponse | null>(null)
  const [evaluationError, setEvaluationError] = useState<string | null>(null)
  const [commitMessage, setCommitMessage] = useState('')
  const [savingAfterReview, setSavingAfterReview] = useState(false)

  const currentUser = useCurrentUser()
  const currentUserId = currentUser?.id ?? null
  const isAdmin = checkAdmin(currentUser)
  const isMaster = branch?.branch_type === 'master'
  const isStandard = branch?.branch_type === 'standard'
  const isOwner = branch?.user_id === currentUserId
  const isPlatformLocked = skill?.platform_locked === true
  const canEditBranch = isPlatformLocked
    ? isAdmin && isStandard
    : !isMaster || isAdmin
  const canMerge = isAdmin && !isMaster && isLatestVersion && !isPlatformLocked

  useEffect(() => {
    if (selectedVersion) {
      const f = versionToForm(selectedVersion)
      setForm(f)
      setRawText(compileToRaw(f))
    } else {
      setForm({ ...EMPTY_9D })
      setRawText('')
    }
    setCommitMessage('')
  }, [selectedVersionId])

  useEffect(() => {
    if (versions.length > 0 && selectedVersionId === null) {
      setSelectedVersionId(versions[0].id)
    }
  }, [versions])

  const handleModeChange = (next: 'structured' | 'raw') => {
    if (next === editMode) return
    if (next === 'raw') {
      setRawText(compileToRaw(form))
    } else {
      const { form: parsed, warnings } = parseToFormData(rawText)
      setForm(parsed)
      if (warnings.length > 0) {
        message.warning(`以下章节未被识别，请检查标题名称:\n${warnings.join('\n')}`, 6)
      }
    }
    setEditMode(next)
  }

  const updateField = (k: NineDimsKey, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const evaluateMutation = useMutation({
    mutationFn: (data: typeof EMPTY_9D) =>
      skillsApi.evaluateDraft(skillId!, parseInt(branchId || ''), {
        role: data.role, profile: data.profile, background: data.background, goals: data.goals,
        constraints: data.constraints, core_skills: data.core_skills, workflows: data.workflows,
        output_format: data.output_format, initialization: data.initialization,
      }),
    onSuccess: (res) => {
      if (!res.data.diff_summary && !res.data.evaluation && !res.data.suggestions) {
        setEvaluationError('AI 评估服务暂时不可用，您仍可跳过审查直接提交。')
      } else {
        setEvaluationResult(res.data)
      }
    },
    onError: (err: any) => {
      setEvaluationError(err.response?.data?.detail || err.message || '评估请求失败，您仍可跳过审查直接提交。')
    },
    onSettled: () => {
      setIsEvaluating(false)
    },
  })

  const createVersionMutation = useMutation({
    mutationFn: (data: { draft: typeof EMPTY_9D; commitMessage?: string }) =>
      skillsApi.createVersion(skillId!, parseInt(branchId || ''), {
        ...data.draft, commit_message: data.commitMessage || 'Update prompt',
      }),
    onSuccess: (res) => {
      message.success(`新版本 v${res.data.version_num} 已保存`)
      setIsCommitModalVisible(false)
      setEvaluationResult(null)
      setEvaluationError(null)
      setCommitMessage('')
      queryClient.invalidateQueries({ queryKey: ['versions', skillId, branchId] })
      setSelectedVersionId(res.data.id)
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '保存失败')
    },
  })

  const mergeMutation = useMutation({
    mutationFn: () => skillsApi.merge(skillId!, {
      source_version_id: versions[0]?.id,
      commit_message: `Merge v${versions[0]?.version_num} to master`,
    }),
    onSuccess: () => {
      message.success('已合并最新版本到 master')
      queryClient.invalidateQueries({ queryKey: ['versions', skillId, branchId] })
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || '合并失败')
    },
  })

  const forkMutation = useMutation({
    mutationFn: () => skillsApi.fork(skillId!, parseInt(branchId || '')),
    onSuccess: (res) => {
      message.success('已 Fork 到你的 personal 分支')
      navigate(`/skill/${skillId}/branch/${res.data.branch.id}`)
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || 'Fork 失败')
    },
  })

  const handleCommit = () => {
    if (!isLatestVersion || !canEditBranch) return
    let draft = form
    if (editMode === 'raw') {
      const { form: parsed, warnings } = parseToFormData(rawText)
      draft = parsed
      setForm(parsed)
      if (warnings.length > 0) {
        message.warning(`以下章节未被识别，请检查标题名称:\n${warnings.join('\n')}`, 6)
      }
    }
    if (!draft.role.trim()) {
      message.warning('Role（角色）必填')
      return
    }
    setIsCommitModalVisible(true)
    setIsEvaluating(true)
    setEvaluationResult(null)
    setEvaluationError(null)
    setCommitMessage('')
    evaluateMutation.mutate(draft)
  }

  const doFinalSave = (skipReview = false) => {
    let draft = form
    if (editMode === 'raw') {
      const { form: parsed, warnings } = parseToFormData(rawText)
      draft = parsed
      if (warnings.length > 0) {
        message.warning(`以下章节未被识别，请检查标题名称:\n${warnings.join('\n')}`, 6)
      }
    }
    if (!draft.role.trim()) {
      message.warning('Role（角色）必填')
      return
    }
    setSavingAfterReview(true)
    createVersionMutation.mutate({ draft, commitMessage })
  }

  const renderTimelineCard = (v: SkillVersion, idx: number) => {
    const selected = v.id === selectedVersionId
    const isLatest = idx === 0
    const summary = (v.ai_commit_summary && v.ai_commit_summary.trim())
      || v.commit_message || '（无摘要）'
    return (
      <div
        key={v.id}
        onClick={() => setSelectedVersionId(v.id)}
        style={{
          padding: 12, marginBottom: 10, borderRadius: 6, cursor: 'pointer',
          background: selected ? 'rgba(0,112,243,0.08)' : 'var(--color-bg)',
          border: selected ? '1px solid var(--color-primary)' : '1px solid var(--color-border)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <Space size={6}>
            <Tag color="cyan" style={{ margin: 0 }}>v{v.version_num}</Tag>
            <Tag style={{ margin: 0 }}>rev {v.revision ?? 0}</Tag>
            {v.source_version_id && <Tag color="purple" style={{ margin: 0 }}>溯源</Tag>}
            {isLatest && <Tag color="green" style={{ margin: 0 }}><ClockCircleOutlined /> HEAD</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 11 }}>{v.created_at?.slice(0, 16) || ''}</Text>
        </div>
        <div style={{
          color: selected ? 'var(--color-text)' : 'var(--color-text-secondary)',
          fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          maxHeight: 60, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical',
        }}>
          {summary}
        </div>
      </div>
    )
  }

  const renderEditor = () => {
    if (!selectedVersion) {
      return (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--color-text-secondary)' }}>
          <HistoryOutlined style={{ fontSize: 36, marginBottom: 12 }} />
          <div>请在左侧选择一条版本快照查看</div>
        </div>
      )
    }
    const disabled = !isLatestVersion || !canEditBranch
    return (
      <>
        {disabled && !isLatestVersion && (
          <Alert type="warning" showIcon style={{ marginBottom: 20 }}
            message={<span>⚠️ 当前正在查看历史版本 v{selectedVersion.version_num}，<Text strong>只读模式</Text>。如要修改请切到最新版本（HEAD）。</span>}
          />
        )}
        {disabled && isLatestVersion && isMaster && !isAdmin && (
          <Alert type="info" showIcon style={{ marginBottom: 20 }}
            message={<span>master 为发布主干，<Text strong>仅 Admin 可编辑</Text>。请在自己的 personal 分支修改后，由 Admin Merge 发布。</span>}
          />
        )}
        {editMode === 'structured' ? (
          NINE_DIMS.map((d) => (
            <div key={d.key} style={{ marginBottom: 18 }}>
              <Text strong style={{ color: 'var(--color-text)' }}>
                {d.label}{d.required && <span style={{ color: '#ff4d4f' }}> *</span>}
              </Text>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>💡 {d.guide}</Text>
              <Input.TextArea
                rows={d.rows}
                value={form[d.key as NineDimsKey]}
                placeholder={d.placeholder}
                onChange={(e) => updateField(d.key as NineDimsKey, e.target.value)}
                disabled={disabled}
              />
            </div>
          ))
        ) : (
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
              🧊 纯文本模式：使用 <code style={{ color: 'var(--color-primary)' }}>### Role</code> 等标题切分 9 个维度。
            </Text>
            <Input.TextArea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              disabled={disabled}
              autoSize={{ minRows: 30, maxRows: 60 }}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.7 }}
            />
          </div>
        )}
      </>
    )
  }

  const renderCommitModal = () => (
    <Modal
      title={<span><ExperimentOutlined style={{ marginRight: 8, color: 'var(--color-primary)' }} />Pre-Commit 审查 · 提交新版本</span>}
      open={isCommitModalVisible}
      onCancel={() => { if (savingAfterReview) return; setIsCommitModalVisible(false); setEvaluationResult(null); setEvaluationError(null) }}
      footer={null} width={780} destroyOnClose
    >
      {isEvaluating ? (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
          <div style={{ marginTop: 16, color: 'var(--color-text-secondary)' }}>AI 正在审查您的 Prompt 变更...</div>
        </div>
      ) : (
        <>
          {evaluationError && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="评估失败" description={evaluationError} />}
          {evaluationResult && (
            <>
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ color: 'var(--color-text)' }}>🤖 AI 审查意见</Text>
                <div style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 4, padding: 12, marginTop: 6, color: 'var(--color-text)', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
                  {evaluationResult.evaluation || '（无）'}
                </div>
              </div>
              {evaluationResult.suggestions && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong style={{ color: 'var(--color-text)' }}>💡 改进建议</Text>
                  <div style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 4, padding: 12, marginTop: 6, color: 'var(--color-text)', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 160, overflowY: 'auto' }}>
                    {evaluationResult.suggestions}
                  </div>
                </div>
              )}
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ color: 'var(--color-text)' }}>📝 变更总结</Text>
                <div style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 4, padding: 12, marginTop: 6, color: 'var(--color-text)', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 120, overflowY: 'auto' }}>
                  {evaluationResult.diff_summary || '（无）'}
                </div>
              </div>
            </>
          )}
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ color: 'var(--color-text)' }}>💬 提交说明</Text>
            <Input value={commitMessage} placeholder="例：优化 Constraints / 修复初始化语序" onChange={(e) => setCommitMessage(e.target.value)} style={{ marginTop: 6 }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            {evaluationError && (
              <Button danger icon={<RocketOutlined />} onClick={() => doFinalSave(true)} loading={savingAfterReview}>
                跳过审查直接提交
              </Button>
            )}
            <Button type="primary" size="large" icon={<RocketOutlined />} onClick={() => doFinalSave(false)} loading={savingAfterReview} disabled={isEvaluating}>
              确认提交
            </Button>
          </div>
        </>
      )}
    </Modal>
  )

  return (
    <div style={{ background: 'var(--color-bg-secondary)', minHeight: 'calc(100vh - 64px)' }}>
      <div style={{
        padding: '10px 24px', borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-bg)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
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
                <span onClick={() => navigate(`/skill/${skillId}`)} style={{ cursor: 'pointer', color: 'var(--color-primary)' }}>
                  <ApartmentOutlined style={{ marginRight: 4 }} />
                  {skill?.display_name || '...'}
                </span>
              ),
            },
            {
              title: (
                <span>
                  {branch?.username || '...'}
                  {isMaster && <Tag color="green" style={{ marginLeft: 4 }}><CrownOutlined /> Master</Tag>}
                  {isStandard && <Tag color="blue" style={{ marginLeft: 4 }}><ProfileOutlined /> Standard</Tag>}
                  {isOwner && !isMaster && !isStandard && <Tag color="purple" style={{ marginLeft: 4 }}><HomeOutlined /> 我的分支</Tag>}
                </span>
              ),
            },
          ]}
        />
        <Text type="secondary" style={{ fontSize: 12 }}><BranchesOutlined /> branch#{branchId} · {versions.length} versions</Text>
      </div>

      <div style={{ display: 'flex', height: 'calc(100vh - 64px - 41px)' }}>
        <div style={{
          width: '30%', minWidth: 280, maxWidth: 380, height: '100%', display: 'flex', flexDirection: 'column',
          borderRight: '1px solid var(--color-border)', background: 'var(--color-bg)',
        }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text strong style={{ color: 'var(--color-text)' }}><HistoryOutlined style={{ marginRight: 6, color: 'var(--color-primary)' }} />版本时间线</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{versions.length} snapshots</Text>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
            {versionsLoading ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
              : versions.length === 0 ? <div style={{ textAlign: 'center', padding: 60, color: 'var(--color-text-secondary)' }}>该 Branch 暂无版本快照</div>
              : versions.map((v, idx) => renderTimelineCard(v, idx))}
          </div>
        </div>

        <div style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column' }}>
          <div style={{
            padding: '14px 28px', borderBottom: '1px solid var(--color-border)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            background: !isLatestVersion ? 'var(--color-bg)' : 'var(--color-bg-secondary)',
          }}>
            <Space size={12} align="center">
              <Text strong style={{ color: 'var(--color-text)', fontSize: 15 }}>
                <EditOutlined style={{ marginRight: 6, color: !isLatestVersion ? 'var(--color-text-secondary)' : 'var(--color-primary)' }} />
                九维工作台
              </Text>
              {selectedVersion && <Tag color="cyan" style={{ margin: 0 }}>v{selectedVersion.version_num}</Tag>}
              {!isLatestVersion ? <Tag color="orange" style={{ margin: 0 }}><EyeOutlined /> HISTORY · 只读</Tag>
                : isPlatformLocked && !canEditBranch ? <Tag color="default" style={{ margin: 0 }}><EyeOutlined /> 平台内置 · 只读</Tag>
                : !canEditBranch ? <Tag color="default" style={{ margin: 0 }}><EyeOutlined /> MASTER · 只读</Tag>
                : <Tag color="green" style={{ margin: 0 }}><EditOutlined /> EDIT · 可编辑</Tag>}
            </Space>
            <Space>
              {isLatestVersion && (
                <Radio.Group value={editMode} onChange={(e) => handleModeChange(e.target.value)} optionType="button" size="small">
                  <Radio.Button value="structured"><ExperimentOutlined /> 结构化</Radio.Button>
                  <Radio.Button value="raw"><CodeOutlined /> 纯文本</Radio.Button>
                </Radio.Group>
              )}
              {isStandard && !isOwner && !isPlatformLocked && <Button size="small" icon={<ForkOutlined />} loading={forkMutation.isPending} onClick={() => forkMutation.mutate()}>Fork 到我的分支</Button>}
              {canMerge && <Button size="small" type="primary" icon={<ArrowUpOutlined />} loading={mergeMutation.isPending} onClick={() => mergeMutation.mutate()} style={{ background: '#722ed1', borderColor: '#722ed1' }}>合并到主干</Button>}
            </Space>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px 60px' }}>
            {versionsLoading ? <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div> : renderEditor()}
          </div>
          {isLatestVersion && selectedVersion && canEditBranch && (
            <div style={{
              position: 'sticky', bottom: 0, padding: '14px 28px',
              background: 'linear-gradient(to top, var(--color-bg-secondary) 70%, transparent)',
              borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'flex-end',
            }}>
              <Button type="primary" size="large" icon={<RocketOutlined />} onClick={handleCommit}>提交新版本 (Commit)</Button>
            </div>
          )}
        </div>
      </div>
      {renderCommitModal()}
    </div>
  )
}
