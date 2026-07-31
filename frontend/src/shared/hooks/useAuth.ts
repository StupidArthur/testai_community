import { useEffect, useState } from 'react'
import { authApi } from '../api/client'
import type { User } from '../types/models'

/** 从 localStorage 同步读取当前用户（路由守卫等非 Hook 场景也可用）。 */
export function getCurrentUser(): User | null {
  try {
    const raw = localStorage.getItem('user')
    if (!raw) return null
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

/** 调用后端刷新当前用户并写入 localStorage。 */
export async function refreshCurrentUser(): Promise<User | null> {
  const token = localStorage.getItem('token')
  if (!token) return null
  try {
    const res = await authApi.currentUser()
    const user = res.data
    localStorage.setItem('user', JSON.stringify(user))
    return user
  } catch {
    return getCurrentUser()
  }
}

/** 登录态下从后端拉取最新用户信息（App 启动时调用）。 */
export function useAuthBootstrap(): void {
  useEffect(() => {
    if (localStorage.getItem('token')) {
      void refreshCurrentUser()
    }
  }, [])
}

/** 读取当前登录用户；挂载时会尝试从 /auth/current-user 刷新。 */
export function useCurrentUser(): User | null {
  const { user } = useAuthSession()
  return user
}

/**
 * 带 ready 的会话状态：ready=false 表示尚未完成 /current-user 刷新。
 * AdminRoute 等守卫应等待 ready 后再判权。
 */
export function useAuthSession(): { user: User | null; ready: boolean } {
  const [user, setUser] = useState<User | null>(() => getCurrentUser())
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setUser(null)
      setReady(true)
      return
    }
    void refreshCurrentUser().then((u) => {
      setUser(u)
      setReady(true)
    })
  }, [])

  return { user, ready }
}

export function isAdmin(user: User | null | undefined): boolean {
  return user?.role === 'Admin'
}

/** 项目管理测试管理员：Admin 或 Manager */
export function isTmAdmin(user: User | null | undefined): boolean {
  return user?.role === 'Admin' || user?.role === 'Manager'
}
