import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Col, Row, Space, Tag, Typography } from 'antd'
import { useParams } from 'react-router-dom'

import { createPracticeSessionForItem } from '../api/practice'
import { getProblem } from '../api/problems'
import { CoachPanel } from './workspace/CoachPanel'
import { ProblemPane } from './workspace/ProblemPane'

export function WorkspacePage() {
  const { itemId, slug } = useParams()
  const isItemRoute = itemId !== undefined
  const isValidItemRoute = itemId ? /^[1-9]\d*$/.test(itemId) : false
  const itemIdNumber = isValidItemRoute ? Number(itemId) : null
  const sessionQuery = useQuery({
    queryKey: ['practice-session', 'plan-item', itemIdNumber],
    queryFn: () => createPracticeSessionForItem(itemIdNumber ?? 0),
    enabled: isItemRoute && isValidItemRoute,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  })
  const problemSlug = sessionQuery.data?.problem_slug ?? slug
  const { data: problem, isError, isLoading } = useQuery({
    queryKey: ['problem', problemSlug],
    queryFn: () => getProblem(problemSlug ?? ''),
    enabled: Boolean(problemSlug) && (!isItemRoute || Boolean(sessionQuery.data)),
  })

  if (!slug && !isItemRoute) {
    return (
      <section className="page-section workspace-grid">
        <Typography.Title level={2}>做题工作台</Typography.Title>
        <Alert showIcon type="info" message="请先从题库选择一道题目。" />
      </section>
    )
  }

  if (isItemRoute && !isValidItemRoute) {
    return (
      <section className="page-section workspace-grid">
        <Typography.Title level={2}>做题工作台</Typography.Title>
        <Alert showIcon type="error" message="计划题入口无效" />
      </section>
    )
  }

  if (isItemRoute && sessionQuery.isLoading) {
    return (
      <section className="page-section workspace-grid">
        <Typography.Title level={2}>做题工作台</Typography.Title>
        <Typography.Text type="secondary">训练会话加载中</Typography.Text>
      </section>
    )
  }

  return (
    <section className="page-section workspace-grid">
      <div className="page-heading">
        <div className="workspace-title-stack">
          <Typography.Title level={2}>做题工作台</Typography.Title>
          {problem ? (
            <Space wrap>
              <span>
                {problem.frontend_id}. {problem.title} {problem.translated_title}
              </span>
              <Tag>{problem.difficulty}</Tag>
              <Button href={problem.leetcode_url} target="_blank" rel="noreferrer">
                LeetCode 原题
              </Button>
            </Space>
          ) : null}
        </div>
      </div>

      {sessionQuery.isError ? (
        <Alert
          showIcon
          type="error"
          message="训练会话加载失败"
          className="page-alert"
        />
      ) : null}

      {isError ? (
        <Alert
          showIcon
          type="error"
          message="题目加载失败"
          className="page-alert"
        />
      ) : null}

      <Row className="workspace-content-row" gutter={[16, 16]}>
        <Col className="workspace-content-column" xs={24} lg={12}>
          <ProblemPane markdown={problem?.statement_md} isLoading={isLoading} />
        </Col>
        <Col className="workspace-content-column" xs={24} lg={12}>
          {sessionQuery.data ? (
            <CoachPanel
              session={sessionQuery.data}
              onSessionRefresh={() => {
                void sessionQuery.refetch()
              }}
            />
          ) : (
            <div className="workspace-pane">
              <h3>教练</h3>
              <Typography.Text type="secondary">从学习计划进入后启用 AI 教练。</Typography.Text>
            </div>
          )}
        </Col>
      </Row>
    </section>
  )
}
