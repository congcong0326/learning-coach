import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Space, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

import {
  getCurrentStudyPlan,
  updatePlanItemStatus,
  type StudyPlanItem,
} from '../api/learning'

const studyPlanQueryKey = ['study-plan', 'current']

const itemStatusMeta: Record<string, { label: string; color: string }> = {
  pending: { label: '未开始', color: 'default' },
  in_progress: { label: '编码中', color: 'blue' },
  completed: { label: '已AC', color: 'green' },
  skipped: { label: '已跳过', color: 'orange' },
  locked_completed: { label: '已AC', color: 'green' },
}

function itemStatusLabel(status: string) {
  return itemStatusMeta[status]?.label ?? status
}

function itemStatusColor(status: string) {
  return itemStatusMeta[status]?.color
}

export function StudyPlanPage() {
  const queryClient = useQueryClient()
  const { data, isError, isLoading } = useQuery({
    queryKey: studyPlanQueryKey,
    queryFn: getCurrentStudyPlan,
    retry: false,
  })
  const itemStatusMutation = useMutation({
    mutationFn: ({ item, status }: { item: StudyPlanItem; status: 'pending' | 'skipped' }) =>
      updatePlanItemStatus(item.id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: studyPlanQueryKey }),
  })

  if (isLoading) {
    return <section className="page-section">学习计划加载中</section>
  }

  if (isError || !data) {
    return (
      <section className="page-section">
        <Alert
          showIcon
          type="info"
          message="还没有学习计划"
          description="请先完成目标校准。"
          className="page-alert"
        />
        <Link to="/goal-calibration">
          <Button type="primary">开始目标校准</Button>
        </Link>
      </section>
    )
  }

  return (
    <section className="page-section study-plan-page">
      <div className="page-heading">
        <Space orientation="vertical" size={2}>
          <Typography.Title level={2}>{data.title}</Typography.Title>
          <Space wrap>
            <Tag color="green">{data.status}</Tag>
            <Tag>v{data.active_version.version_number}</Tag>
            <Tag>
              {String(data.active_version.target_snapshot.preferred_language ?? '')}
            </Tag>
          </Space>
        </Space>
      </div>

      <Typography.Paragraph>
        {data.active_version.generation_summary_md}
      </Typography.Paragraph>

      {data.active_version.stages.map((stage) => (
        <section key={stage.id} className="plan-stage">
          <div className="plan-stage-heading">
            <Typography.Title level={3}>{stage.title}</Typography.Title>
            <Tag>{stage.status}</Tag>
          </div>
          <Typography.Paragraph>{stage.objective_md}</Typography.Paragraph>
          <div className="plan-items">
            {stage.items.map((item) => (
              <div key={item.id} className="plan-item-row">
                <div>
                  <Link to={`/workspace/items/${item.id}`}>
                    <span>{item.frontend_id}.</span> <span>{item.title}</span>
                  </Link>
                  <Typography.Text type="secondary">
                    {' '}
                    {item.translated_title}
                  </Typography.Text>
                  <div className="plan-item-reason">
                    {item.recommendation_reason}
                  </div>
                </div>
                <Space wrap>
                  <Tag>{item.difficulty}</Tag>
                  <Tag color={itemStatusColor(item.status)}>
                    {itemStatusLabel(item.status)}
                  </Tag>
                  {item.status === 'pending' ? (
                    <Button
                      onClick={() =>
                        itemStatusMutation.mutate({ item, status: 'skipped' })
                      }
                      loading={
                        itemStatusMutation.isPending &&
                        itemStatusMutation.variables?.item.id === item.id
                      }
                    >
                      跳过
                    </Button>
                  ) : null}
                  {item.status === 'skipped' ? (
                    <Button
                      onClick={() =>
                        itemStatusMutation.mutate({ item, status: 'pending' })
                      }
                      loading={
                        itemStatusMutation.isPending &&
                        itemStatusMutation.variables?.item.id === item.id
                      }
                    >
                      取消跳过
                    </Button>
                  ) : null}
                </Space>
              </div>
            ))}
          </div>
        </section>
      ))}
    </section>
  )
}
