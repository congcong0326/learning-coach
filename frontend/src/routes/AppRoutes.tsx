import { Navigate, Route, Routes } from 'react-router-dom'

import { ProblemDetailPage } from '../pages/ProblemDetailPage'
import { ProblemLibraryPage } from '../pages/ProblemLibraryPage'
import { AuthRedirect } from './AuthRedirect'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AuthRedirect />} />
      <Route path="/problems" element={<ProblemLibraryPage />} />
      <Route path="/problems/:slug" element={<ProblemDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
