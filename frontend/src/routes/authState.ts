import { useQuery } from '@tanstack/react-query'

import { getCurrentUser } from '../api/auth'

export const currentUserQueryKey = ['current-user']

export function useCurrentUserQuery() {
  return useQuery({
    queryKey: currentUserQueryKey,
    queryFn: getCurrentUser,
    retry: false,
  })
}
