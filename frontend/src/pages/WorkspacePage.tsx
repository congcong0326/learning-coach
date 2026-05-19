import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Col, Row, Space, Tag, Typography } from 'antd'
import { Fragment } from 'react'
import { useParams } from 'react-router-dom'

import { getProblem } from '../api/problems'

function StatementText({ markdown }: { markdown: string }) {
  return (
    <pre className="markdown-statement">
      {markdown.split('\n').map((line, index) => (
        <Fragment key={`${line}-${index}`}>
          <span>{line}</span>
          {'\n'}
        </Fragment>
      ))}
    </pre>
  )
}

export function WorkspacePage() {
  const { slug } = useParams()
  const { data: problem, isError, isLoading } = useQuery({
    queryKey: ['problem', slug],
    queryFn: () => getProblem(slug ?? ''),
    enabled: Boolean(slug),
  })

  if (!slug) {
    return (
      <section className="page-section workspace-grid">
        <Typography.Title level={2}>做题工作台</Typography.Title>
        <Alert showIcon type="info" message="请先从题库选择一道题目。" />
      </section>
    )
  }

  return (
    <section className="page-section workspace-grid">
      <div className="page-heading">
        <Space direction="vertical" size={2}>
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
        </Space>
      </div>

      {isError ? (
        <Alert
          showIcon
          type="error"
          message="题目加载失败"
          className="page-alert"
        />
      ) : null}

      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <div className="workspace-pane">
            <h3>题面</h3>
            {isLoading ? (
              <Typography.Text type="secondary">题面加载中</Typography.Text>
            ) : null}
            {problem ? <StatementText markdown={problem.statement_md} /> : null}
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="workspace-pane">
            <h3>代码</h3>
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="workspace-pane">
            <h3>教练</h3>
          </div>
        </Col>
      </Row>
    </section>
  )
}
