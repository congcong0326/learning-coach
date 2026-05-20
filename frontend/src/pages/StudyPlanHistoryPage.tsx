import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Space, Table, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

import {
  activateStudyPlan,
  listStudyPlans,
  type StudyPlanListResponse,
} from '../api/learning'

const studyPlanListQueryKey = ['study-plans']

type StudyPlanListItem = StudyPlanListResponse['items'][number]

export function StudyPlanHistoryPage() {
  const queryClient = useQueryClient()
  const { data, isError, isLoading } = useQuery({
    queryKey: studyPlanListQueryKey,
    queryFn: listStudyPlans,
  })
  const activateMutation = useMutation({
    mutationFn: activateStudyPlan,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: studyPlanListQueryKey }),
  })

  return (
    <section className="page-section">
      <div className="page-heading">
        <Typography.Title level={2}>学习计划历史</Typography.Title>
        <Link to="/goal-calibration">
          <Button type="primary">新建计划</Button>
        </Link>
      </div>

      {isError ? (
        <Alert
          showIcon
          type="error"
          message="计划列表加载失败"
          className="page-alert"
        />
      ) : null}

      <Table<StudyPlanListItem>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.items ?? []}
        columns={[
          { title: '计划名称', dataIndex: 'title' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: string) => <Tag>{status}</Tag>,
          },
          {
            title: '当前版本',
            dataIndex: 'active_version_number',
            render: (value: number) => `v${value}`,
          },
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Link to="/study-plan">
                  <Button>查看</Button>
                </Link>
                {row.status === 'paused' || row.status === 'completed' ? (
                  <Button
                    type="primary"
                    aria-label="激活"
                    onClick={() => activateMutation.mutate(row.id)}
                    loading={
                      activateMutation.isPending &&
                      activateMutation.variables === row.id
                    }
                  >
                    激活
                  </Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
    </section>
  )
}
