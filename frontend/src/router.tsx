import { createBrowserRouter, Navigate } from 'react-router-dom'
import Login from './auth/Login'
import Dashboard from './skill_hub/pages/Dashboard'
import SkillBranches from './skill_hub/pages/SkillBranches'
import BranchSandbox from './skill_hub/pages/BranchSandbox'
import AdminPage from './skill_hub/pages/AdminPage'
import AppLayout from './shared/components/AppLayout'
import Portal from './shared/pages/Portal'
import TranslateHomePage from './translate/pages/HomePage'
import TranslateJobDetailPage from './translate/pages/JobDetailPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
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
        path: 'skills',
        element: <Dashboard />,
      },
      {
        path: 'skill/:skillId',
        element: <SkillBranches />,
      },
      {
        path: 'skill/:skillId/branch/:branchId',
        element: <BranchSandbox />,
      },
      {
        path: 'admin',
        element: <AdminPage />,
      },
      {
        path: 'translate',
        element: <TranslateHomePage />,
      },
      {
        path: 'translate/jobs/:jobId',
        element: <TranslateJobDetailPage />,
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
