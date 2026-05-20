import { Navigate, Route, Routes } from 'react-router-dom'
import { Typography } from 'antd'

import { ApiKeySettingsPage } from '../pages/ApiKeySettingsPage'
import { ProblemLibraryPage } from '../pages/ProblemLibraryPage'
import { ReviewPage } from '../pages/ReviewPage'
import { TracePage } from '../pages/TracePage'
import { WorkspacePage } from '../pages/WorkspacePage'
import { AuthRedirect } from './AuthRedirect'

function GoalCalibrationPagePlaceholder() {
  return (
    <section className="page-section">
      <Typography.Title level={2}>目标校准</Typography.Title>
    </section>
  )
}

function StudyPlanPagePlaceholder() {
  return (
    <section className="page-section">
      <Typography.Title level={2}>学习计划</Typography.Title>
    </section>
  )
}

function StudyPlanHistoryPagePlaceholder() {
  return (
    <section className="page-section">
      <Typography.Title level={2}>学习计划历史</Typography.Title>
    </section>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AuthRedirect />} />
      <Route path="/settings/api-keys" element={<ApiKeySettingsPage />} />
      <Route path="/problems" element={<ProblemLibraryPage />} />
      <Route path="/goal-calibration" element={<GoalCalibrationPagePlaceholder />} />
      <Route path="/study-plan" element={<StudyPlanPagePlaceholder />} />
      <Route path="/study-plans" element={<StudyPlanHistoryPagePlaceholder />} />
      <Route
        path="/study-plans/:planId/versions/:versionId"
        element={<StudyPlanPagePlaceholder />}
      />
      <Route path="/workspace" element={<WorkspacePage />} />
      <Route path="/workspace/:slug" element={<WorkspacePage />} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/trace" element={<TracePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
