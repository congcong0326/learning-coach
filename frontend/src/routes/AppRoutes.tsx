import { Navigate, Route, Routes } from 'react-router-dom'

import { ApiKeySettingsPage } from '../pages/ApiKeySettingsPage'
import { DashboardPage } from '../pages/DashboardPage'
import { GoalCalibrationPage } from '../pages/GoalCalibrationPage'
import { ProblemLibraryPage } from '../pages/ProblemLibraryPage'
import { ReviewPage } from '../pages/ReviewPage'
import { StudyPlanHistoryPage } from '../pages/StudyPlanHistoryPage'
import { StudyPlanPage } from '../pages/StudyPlanPage'
import { TracePage } from '../pages/TracePage'
import { WorkspacePage } from '../pages/WorkspacePage'
import { AuthRedirect } from './AuthRedirect'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AuthRedirect />} />
      <Route path="/settings/api-keys" element={<ApiKeySettingsPage />} />
      <Route path="/problems" element={<ProblemLibraryPage />} />
      <Route path="/goal-calibration" element={<GoalCalibrationPage />} />
      <Route path="/study-plan" element={<StudyPlanPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/study-plans" element={<StudyPlanHistoryPage />} />
      <Route
        path="/study-plans/:planId/versions/:versionId"
        element={<StudyPlanPage />}
      />
      <Route path="/workspace" element={<WorkspacePage />} />
      <Route path="/workspace/items/:itemId" element={<WorkspacePage />} />
      <Route path="/workspace/:slug" element={<WorkspacePage />} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/trace" element={<TracePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
