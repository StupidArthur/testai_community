import { useState, useEffect } from 'react'
import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'
import { Spin } from 'antd'
import Login from './auth/Login'
import Dashboard from './skill_hub/pages/Dashboard'
import SkillBranches from './skill_hub/pages/SkillBranches'
import SkillDebugPage from './skill_hub/pages/SkillDebugPage'
import BranchSandbox from './skill_hub/pages/BranchSandbox'
import AdminPage from './skill_hub/pages/AdminPage'
import AppLayout from './shared/components/AppLayout'
import Portal from './shared/pages/Portal'
import TranslateHomePage from './translate/pages/HomePage'
import TranslateJobDetailPage from './translate/pages/JobDetailPage'
import ChangelogPage from './changelog/ChangelogPage'
import DailyReportPage from './daily_report/pages/DailyReportPage'
import ToolHubPage from './tool_hub/pages/ToolHubPage'
import ToolDetailPage from './tool_hub/pages/ToolDetailPage'
import KnowledgeHubPage from './knowledge_base/pages/KnowledgeHubPage'
import CleanJobReviewPage from './data_cleaning/pages/CleanJobReviewPage'
import AnchorDictPage from './data_cleaning/pages/AnchorDictPage'
import ProjectManagePage from './test_manage/pages/ProjectManagePage'
import { refreshCurrentUser, isAdmin } from './shared/hooks/useAuth'

function decodeJWTPayload(token: string): Record<string, unknown> | null {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(base64))
  } catch {
    return null
  }
}

function hasValidToken(): boolean {
  const token = localStorage.getItem('token')
  if (!token) return false
  const payload = decodeJWTPayload(token)
  if (!payload || !payload.exp) return false
  return (payload.exp as number) * 1000 > Date.now()
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!hasValidToken()) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function GuestRoute({ children }: { children: React.ReactNode }) {
  if (hasValidToken()) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)
  const [allowed, setAllowed] = useState(false)

  useEffect(() => {
    if (!hasValidToken()) {
      setAllowed(false)
      setReady(true)
      return
    }
    void refreshCurrentUser().then((user) => {
      setAllowed(isAdmin(user))
      setReady(true)
    })
  }, [])

  if (!hasValidToken()) {
    return <Navigate to="/login" replace />
  }
  if (!ready) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin />
      </div>
    )
  }
  if (!allowed) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

function RedirectLegacyCleanJob() {
  const { jobId } = useParams<{ jobId: string }>()
  return <Navigate to={`/knowledge-base/clean/${jobId}`} replace />
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <GuestRoute><Login /></GuestRoute>,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <Portal />,
      },
      {
        path: 'projects',
        element: <ProjectManagePage />,
      },
      {
        path: 'skills',
        element: <Dashboard />,
      },
      {
        path: 'skill/:skillId',
        element: <SkillBranches />,
      },
      {
        path: 'skill/:skillId/debug',
        element: <SkillDebugPage />,
      },
      {
        path: 'skill/:skillId/branch/:branchId',
        element: <BranchSandbox />,
      },
      {
        path: 'admin',
        element: <AdminRoute><AdminPage /></AdminRoute>,
      },
      {
        path: 'translate',
        element: <TranslateHomePage />,
      },
      {
        path: 'translate/jobs/:jobId',
        element: <TranslateJobDetailPage />,
      },
      {
        path: 'changelog',
        element: <ChangelogPage />,
      },
      {
        path: 'daily-reports',
        element: <DailyReportPage />,
      },
      {
        path: 'tool-hub',
        element: <ToolHubPage />,
      },
      {
        path: 'tool-hub/:toolId',
        element: <ToolDetailPage />,
      },
      {
        path: 'data-cleaning',
        element: <Navigate to="/knowledge-base?tab=clean" replace />,
      },
      {
        path: 'data-cleaning/anchors',
        element: <Navigate to="/knowledge-base/anchors" replace />,
      },
      {
        path: 'data-cleaning/:jobId',
        element: <RedirectLegacyCleanJob />,
      },
      {
        path: 'knowledge-base',
        element: <KnowledgeHubPage />,
      },
      {
        path: 'knowledge-base/anchors',
        element: <AdminRoute><AnchorDictPage /></AdminRoute>,
      },
      {
        path: 'knowledge-base/clean/:jobId',
        element: <CleanJobReviewPage />,
      },
      {
        path: 'knowledge-base/:kbId',
        element: <Navigate to="/knowledge-base" replace />,
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
