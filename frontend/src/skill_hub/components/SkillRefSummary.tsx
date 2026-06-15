/**
 * SkillRefSummary：只读展示已选 Skill 引用，可选预览解析结果。
 */
import { Typography, Tag, Space, Button, Spin, Alert } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import type { SkillRef, ResolvedSkill, Skill, Branch } from '../../shared/types/models'

const { Text, Paragraph } = Typography

export interface SkillRefSummaryProps {
  ref: SkillRef
  skill?: Skill | null
  branch?: Branch | null
  showResolvePreview?: boolean
}

function branchLabel(branch: Branch | null | undefined): string {
  if (!branch) return '—'
  if (branch.branch_type === 'personal') return `${branch.username}/personal`
  return branch.branch_type
}

export default function SkillRefSummary({
  ref: skillRef,
  skill,
  branch,
  showResolvePreview = true,
}: SkillRefSummaryProps) {
  const resolveMut = useMutation({
    mutationFn: () => skillsApi.resolve(skillRef).then((r) => r.data),
  })

  const modeLabel = skillRef.resolve_mode === 'pinned' ? '锁定快照' : '跟随 HEAD'

  return (
    <div style={{ padding: '8px 0' }}>
      <Space wrap>
        <Tag color={skillRef.resolve_mode === 'pinned' ? 'orange' : 'blue'}>{modeLabel}</Tag>
        {skill && <Text strong>{skill.display_name}</Text>}
        {skill && <Text type="secondary">({skill.name})</Text>}
        {branch && <Tag>{branchLabel(branch)}</Tag>}
        {skillRef.resolve_mode === 'pinned' && skillRef.version_id && (
          <Text type="secondary" copyable={{ text: skillRef.version_id }}>
            id: {skillRef.version_id.slice(0, 8)}…
          </Text>
        )}
      </Space>
      {skillRef.resolve_mode === 'branch_head' && (
        <Paragraph type="secondary" style={{ margin: '8px 0 0', fontSize: 12 }}>
          任务启动时将解析为当时分支 HEAD，并固化 resolved_version_id。
        </Paragraph>
      )}
      {showResolvePreview && (
        <div style={{ marginTop: 8 }}>
          {!resolveMut.data && !resolveMut.isPending && (
            <Button size="small" onClick={() => resolveMut.mutate()}>
              预览解析
            </Button>
          )}
          {resolveMut.isPending && <Spin size="small" />}
          {resolveMut.isError && (
            <Alert type="error" message="解析失败" style={{ marginTop: 8 }} />
          )}
          {resolveMut.data && (
            <Alert
              type="info"
              style={{ marginTop: 8 }}
              message={
                <ResolvedPreview data={resolveMut.data} />
              }
            />
          )}
        </div>
      )}
    </div>
  )
}

function ResolvedPreview({ data }: { data: ResolvedSkill }) {
  return (
    <div>
      <div><Text code>{data.version_locator}</Text></div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        Release #{data.branch_type === 'master' ? data.version_num : '—'} · rev {data.revision}
      </Text>
    </div>
  )
}
