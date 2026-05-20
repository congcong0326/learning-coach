import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useCurrentUserQuery } from './authState'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { data: user, isError, isLoading } = useCurrentUserQuery()

  if (isLoading) {
    return (
      <div className="route-loading" role="status">
        登录状态检查中
      </div>
    )
  }

  if (isError || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (
    !user.has_default_llm_credential &&
    location.pathname !== '/settings/api-keys'
  ) {
    return <Navigate to="/settings/api-keys" replace />
  }

  return <>{children}</>
}
