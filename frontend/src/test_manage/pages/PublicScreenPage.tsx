/**
 * 公开只读作战大屏（免登录）。
 * 深链示例：/tm-screen?view=today&project_id=xxx
 * screenshot=1 时供 Playwright 截图（仍只读）。
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Spin, Typography } from 'antd'
import axios from 'axios'
import type {
  BoardOut,
  TmProject,
  TmUserBrief,
  WeekHistoryOption,
  WeekInfo,
} from '../../shared/api/test-manage'
import { pickDefaultProjectId } from '../utils/boardUi'
import WeekScreenTab from './WeekScreenTab'
import type { WeekViewMode } from './WeekViewSwitcher'
import './WeekScreenTab.css'

const { Text } = Typography

/** 公开 API 不带 token，401 也不跳登录 */
const publicClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

function displayName(u: TmUserBrief) {
  const rn = (u.real_name || '').trim()
  return rn || u.username
}

export default function PublicScreenPage() {
  const [params] = useSearchParams()
  const viewParam = (params.get('view') || 'today').toLowerCase()
  const initialMode: WeekViewMode =
    viewParam === 'history'
      ? 'history'
      : viewParam === 'current'
        ? 'current'
        : viewParam === 'pipeline' || viewParam === 'req'
          ? 'pipeline'
          : 'today'
  const screenshotMode = params.get('screenshot') === '1'
  const initialProject = params.get('project_id') || undefined

  const [weekMode, setWeekMode] = useState<WeekViewMode>(initialMode)
  const [projectId, setProjectId] = useState<string | undefined>(initialProject)
  const [historyWeekStart, setHistoryWeekStart] = useState<string | undefined>()

  const { data: week } = useQuery({
    queryKey: ['tm-public-week'],
    queryFn: async () => (await publicClient.get<WeekInfo>('/test-manage/public/week')).data,
  })

  const projectsQuery = useQuery({
    queryKey: ['tm-public-projects'],
    queryFn: async () =>
      (await publicClient.get<TmProject[]>('/test-manage/public/projects')).data,
  })
  const projects = projectsQuery.data ?? []

  const { data: users = [] } = useQuery({
    queryKey: ['tm-public-users'],
    queryFn: async () =>
      (await publicClient.get<TmUserBrief[]>('/test-manage/public/users')).data,
  })

  const historyOptions: WeekHistoryOption[] = week?.history ?? []

  useEffect(() => {
    if (weekMode !== 'history') return
    if (!historyOptions.length) return
    const stillValid = historyOptions.some((h) => h.week_start === historyWeekStart)
    if (!stillValid) setHistoryWeekStart(historyOptions[0].week_start)
  }, [weekMode, historyOptions, historyWeekStart])

  /**
   * 与登录大屏一致：无 URL project_id 时默认选 TPT（或最新项目），
   * 避免公开页拉「全项目」而登录页只看 TPT 导致数据对不上。
   */
  useEffect(() => {
    if (projectId) return
    if (!projects.length) return
    const pick = pickDefaultProjectId(projects)
    if (pick) setProjectId(pick)
  }, [projects, projectId])

  const boardWeekStart = weekMode === 'history' ? historyWeekStart : undefined
  /** 有项目列表时等默认选中后再请求，避免先拉全量再切 TPT 闪一下 */
  const boardReady =
    Boolean(projectId) || (projectsQuery.isSuccess && projects.length === 0)

  const { data: board, isLoading: boardLoading } = useQuery({
    queryKey: ['tm-public-board', projectId || 'all', boardWeekStart || 'current'],
    queryFn: async () =>
      (
        await publicClient.get<BoardOut>('/test-manage/public/board', {
          params: {
            ...(projectId ? { project_id: projectId } : {}),
            ...(boardWeekStart ? { week_start: boardWeekStart } : {}),
          },
        })
      ).data,
    enabled:
      boardReady &&
      (weekMode === 'today' ||
        weekMode === 'current' ||
        weekMode === 'pipeline' ||
        !!boardWeekStart),
  })

  const userName = useMemo(() => {
    const map = new Map(users.map((u) => [u.id, displayName(u)]))
    return (id: number) => map.get(id) || `用户#${id}`
  }, [users])

  const handleWeekModeChange = (mode: WeekViewMode) => {
    setWeekMode(mode)
    if (mode === 'history' && !historyWeekStart && historyOptions[0]) {
      setHistoryWeekStart(historyOptions[0].week_start)
    }
  }

  if (!week && boardLoading) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin />
      </div>
    )
  }

  return (
    <div
      className={`tm-public-screen${screenshotMode ? ' tm-public-screen--shot' : ''}`}
      style={{ minHeight: '100vh', background: '#f7f9fc', padding: screenshotMode ? 8 : 16 }}
      data-testid="tm-public-screen"
    >
      {!screenshotMode ? (
        <Text className="tm-public-screen__tip">
          只读预览，编辑请登录「项目管理」
        </Text>
      ) : null}
      <WeekScreenTab
        board={board}
        loading={boardLoading}
        projects={projects.map((p) => ({ id: p.id, name: p.name }))}
        projectId={projectId}
        onProjectChange={setProjectId}
        weekMode={weekMode}
        onWeekModeChange={handleWeekModeChange}
        historyOptions={historyOptions}
        historyWeekStart={historyWeekStart}
        onHistoryWeekStartChange={setHistoryWeekStart}
        userName={userName}
        onOpenAction={() => undefined}
        readOnly
        showShare={false}
      />
    </div>
  )
}
