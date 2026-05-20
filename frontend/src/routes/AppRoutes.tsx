import { Navigate, Route, Routes } from 'react-router-dom'

import { ApiKeySettingsPage } from '../pages/ApiKeySettingsPage'
import { ProblemLibraryPage } from '../pages/ProblemLibraryPage'
import { ReviewPage } from '../pages/ReviewPage'
import { TracePage } from '../pages/TracePage'
import { WorkspacePage } from '../pages/WorkspacePage'
import { AuthRedirect } from './AuthRedirect'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AuthRedirect />} />
      <Route path="/settings/api-keys" element={<ApiKeySettingsPage />} />
      <Route path="/problems" element={<ProblemLibraryPage />} />
      <Route path="/workspace" element={<WorkspacePage />} />
      <Route path="/workspace/:slug" element={<WorkspacePage />} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/trace" element={<TracePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
