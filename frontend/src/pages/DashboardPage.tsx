import { useQuery } from '@tanstack/react-query'
import { Alert, Space, Spin, Tag, Typography } from 'antd'

import { getPracticeDashboard } from '../api/dashboard'
import type { HintLevel } from '../api/practice'

const hintLabels: Record<HintLevel, string> = {
  questioning: '追问档',
  direction: '方向档',
  key_hint: '关键档',
  reflection: '复盘档',
}

function hintLabel(value: HintLevel | null) {
  return value ? hintLabels[value] : '-'
}

export function DashboardPage() {
  const dashboardQuery = useQuery({
    queryKey: ['practice-dashboard'],
    queryFn: getPracticeDashboard,
    retry: false,
  })

  if (dashboardQuery.isLoading) {
    return (
      <section className="page-section">
        <Typography.Title level={2}>学习仪表盘</Typography.Title>
        <Spin />
      </section>
    )
  }

  if (dashboardQuery.isError || !dashboardQuery.data) {
    return (
      <section className="page-section">
        <Typography.Title level={2}>学习仪表盘</Typography.Title>
        <Alert showIcon type="error" message="仪表盘加载失败" />
      </section>
    )
  }

  const dashboard = dashboardQuery.data
  return (
    <section className="page-section dashboard-page">
      <Typography.Title level={2}>学习仪表盘</Typography.Title>
      <div className="dashboard-metric-grid">
        <div className="dashboard-metric">
          <span className="dashboard-metric-label">完成题数</span>
          <strong>{dashboard.completed_problem_count}</strong>
        </div>
        <div className="dashboard-metric">
          <span className="dashboard-metric-label">平均提示档位</span>
          <strong>{dashboard.average_hint_gear ?? '-'}</strong>
        </div>
        <div className="dashboard-metric">
          <span className="dashboard-metric-label">最高提示档位</span>
          <strong>{hintLabel(dashboard.highest_hint_level)}</strong>
        </div>
      </div>
      <section className="dashboard-section">
        <Typography.Title level={3}>常见卡点</Typography.Title>
        <Space wrap>
          {dashboard.common_stuck_points.length > 0 ? (
            dashboard.common_stuck_points.map((item) => (
              <Tag key={item.stuck_point}>
                {item.stuck_point} x{item.count}
              </Tag>
            ))
          ) : (
            <span>-</span>
          )}
        </Space>
      </section>
      <section className="dashboard-section">
        <Typography.Title level={3}>最近画像摘要</Typography.Title>
        <Typography.Paragraph>
          {dashboard.recent_profile_summary || '-'}
        </Typography.Paragraph>
      </section>
    </section>
  )
}
