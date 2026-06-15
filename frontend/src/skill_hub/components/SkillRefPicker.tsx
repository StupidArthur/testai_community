/**
 * SkillRefPicker：选择 Skill 引用（模式 → Skill → Branch → 可选版本）。
 * 产出 SkillRef JSON，供业务模块配置存储。
 */
import { useState, useMemo, useEffect } from 'react'
import {
  Modal, Radio, Select, List, Tag, Typography, Space, Button, Empty, Spin, message,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { skillsApi } from '../../shared/api/client'
import type { SkillRef, Skill, Branch, SkillVersion } from '../../shared/types/models'
import SkillRefSummary from './SkillRefSummary'

const { Text } = Typography

export type SkillRefPickerMode = 'branch_head' | 'pinned'

export interface SkillRefPickerProps {
  open: boolean
  onClose: () => void
  value?: SkillRef | null
  onChange: (ref: SkillRef) => void
  categoryFilter?: string
}

function branchOptionLabel(b: Branch): string {
  if (b.branch_type === 'personal') return `personal（${b.username}）`
  if (b.branch_type === 'standard') return `standard（${b.username}）`
  return b.branch_type
}

export default function SkillRefPicker({
  open,
  onClose,
  value,
  onChange,
  categoryFilter,
}: SkillRefPickerProps) {
  const [resolveMode, setResolveMode] = useState<SkillRefPickerMode>(
    value?.resolve_mode ?? 'branch_head',
  )
  const [skillId, setSkillId] = useState<string | null>(null)
  const [branchId, setBranchId] = useState<number | null>(null)
  const [versionId, setVersionId] = useState<string | null>(null)

  const { data: skills = [], isLoading: skillsLoading } = useQuery({
    queryKey: ['skills', categoryFilter],
    queryFn: () => skillsApi.list(categoryFilter).then((r) => r.data),
    enabled: open,
  })

  const { data: branches = [], isLoading: branchesLoading } = useQuery({
    queryKey: ['skill-branches', skillId],
    queryFn: () => skillsApi.listBranches(skillId!).then((r) => r.data),
    enabled: open && !!skillId,
  })

  const { data: versions = [], isLoading: versionsLoading } = useQuery({
    queryKey: ['skill-versions', skillId, branchId],
    queryFn: () => skillsApi.getVersions(skillId!, branchId!).then((r) => r.data),
    enabled: open && !!skillId && !!branchId && resolveMode === 'pinned',
  })

  const selectedSkill = useMemo(
    () => skills.find((s) => s.id === skillId) ?? null,
    [skills, skillId],
  )
  const selectedBranch = useMemo(
    () => branches.find((b) => b.id === branchId) ?? null,
    [branches, branchId],
  )

  useEffect(() => {
    if (!open) return
    if (value?.skill_name && skills.length) {
      const s = skills.find((x) => x.name === value.skill_name)
      if (s) setSkillId(s.id)
    }
    setResolveMode(value?.resolve_mode ?? 'branch_head')
    setBranchId(value?.branch_id ?? null)
    setVersionId(value?.version_id ?? null)
  }, [open, value, skills])

  useEffect(() => {
    if (branchId && branches.length && !branches.some((b) => b.id === branchId)) {
      setBranchId(null)
    }
  }, [branches, branchId])

  const draftRef = useMemo((): SkillRef | null => {
    if (!selectedSkill || !selectedBranch) return null
    if (resolveMode === 'pinned') {
      if (!versionId) return null
      return {
        resolve_mode: 'pinned',
        skill_name: selectedSkill.name,
        version_id: versionId,
        branch_id: selectedBranch.id,
      }
    }
    return {
      resolve_mode: 'branch_head',
      skill_name: selectedSkill.name,
      branch_id: selectedBranch.id,
      branch_type: selectedBranch.branch_type,
      owner_user_id: selectedBranch.branch_type === 'personal' ? selectedBranch.user_id : null,
    }
  }, [selectedSkill, selectedBranch, resolveMode, versionId])

  const handleConfirm = () => {
    if (!draftRef) {
      message.warning(resolveMode === 'pinned' ? '请选择 Skill、分支与版本' : '请选择 Skill 与分支')
      return
    }
    onChange(draftRef)
    onClose()
    message.success('Skill 引用已选择')
  }

  const renderVersionRow = (v: SkillVersion) => {
    const selected = versionId === v.id
    const summary = (v.ai_commit_summary || v.commit_message || '').slice(0, 80)
    return (
      <List.Item
        key={v.id}
        onClick={() => setVersionId(v.id)}
        style={{
          cursor: 'pointer',
          background: selected ? 'var(--ant-color-primary-bg)' : undefined,
          borderRadius: 6,
          padding: '8px 12px',
        }}
      >
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="cyan">v{v.version_num}</Tag>
            <Tag>rev {v.revision}</Tag>
            {v.source_version_id && <Tag color="purple">有溯源</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{summary}</Text>
        </Space>
      </List.Item>
    )
  }

  return (
    <Modal
      title="选择 Skill 引用"
      open={open}
      onCancel={onClose}
      width={720}
      footer={[
        <Button key="cancel" onClick={onClose}>取消</Button>,
        <Button key="ok" type="primary" onClick={handleConfirm} disabled={!draftRef}>
          确认
        </Button>,
      ]}
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Text strong>引用模式</Text>
          <Radio.Group
            value={resolveMode}
            onChange={(e) => {
              setResolveMode(e.target.value)
              setVersionId(null)
            }}
            style={{ display: 'block', marginTop: 8 }}
          >
            <Radio value="branch_head">跟随分支 HEAD（自动更新）</Radio>
            <Radio value="pinned">锁定指定快照</Radio>
          </Radio.Group>
        </div>

        <div>
          <Text strong>Skill</Text>
          <Select
            showSearch
            placeholder="选择 Skill"
            style={{ width: '100%', marginTop: 8 }}
            loading={skillsLoading}
            value={skillId}
            onChange={(id) => {
              setSkillId(id)
              setBranchId(null)
              setVersionId(null)
            }}
            optionFilterProp="label"
            options={skills.map((s: Skill) => ({
              value: s.id,
              label: `${s.display_name} (${s.name})`,
            }))}
          />
        </div>

        {skillId && (
          <div>
            <Text strong>Branch</Text>
            <Select
              placeholder="选择分支"
              style={{ width: '100%', marginTop: 8 }}
              loading={branchesLoading}
              value={branchId}
              onChange={(id) => {
                setBranchId(id)
                setVersionId(null)
              }}
              options={branches.map((b: Branch) => ({
                value: b.id,
                label: branchOptionLabel(b),
              }))}
            />
          </div>
        )}

        {resolveMode === 'pinned' && branchId && (
          <div>
            <Text strong>版本（时间线）</Text>
            {versionsLoading ? (
              <Spin style={{ display: 'block', marginTop: 12 }} />
            ) : versions.length === 0 ? (
              <Empty description="该分支暂无版本" style={{ marginTop: 12 }} />
            ) : (
              <List
                size="small"
                dataSource={versions}
                renderItem={renderVersionRow}
                style={{ maxHeight: 240, overflow: 'auto', marginTop: 8 }}
              />
            )}
          </div>
        )}

        {draftRef && (
          <SkillRefSummary
            ref={draftRef}
            skill={selectedSkill}
            branch={selectedBranch}
            showResolvePreview
          />
        )}
      </Space>
    </Modal>
  )
}
