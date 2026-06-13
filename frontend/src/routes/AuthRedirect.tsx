import { Navigate } from 'react-router-dom'

import { useCurrentUserQuery } from './authState'

export function AuthRedirect() {
  const { data: user, isLoading } = useCurrentUserQuery()

  if (isLoading) {
    return (
      <div className="route-loading" role="status">
        登录状态检查中
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <Navigate to="/problems" replace />
}
