import { ArrowLeftOutlined, LinkOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Descriptions, Skeleton, Space, Tag, Typography } from 'antd'
import { Link, useParams } from 'react-router-dom'

import { getProblem, type ProblemListItem } from '../api/problems'
import { StatementMarkdown } from '../components/StatementMarkdown'

function difficultyColor(difficulty: ProblemListItem['difficulty']) {
  if (difficulty === 'Easy') {
    return 'success'
  }
  if (difficulty === 'Medium') {
    return 'warning'
  }
  return 'error'
}

export function ProblemDetailPage() {
  const { slug } = useParams()
  const { data, isError, isLoading } = useQuery({
    queryKey: ['problem', slug],
    queryFn: () => getProblem(slug ?? ''),
    enabled: Boolean(slug),
  })

  if (isLoading) {
    return (
      <section className="page-section problem-detail">
        <Skeleton active paragraph={{ rows: 8 }} />
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="page-section problem-detail">
        <Alert showIcon type="error" message="题目加载失败" className="page-alert" />
        <Link to="/problems">返回题库</Link>
      </section>
    )
  }

  return (
    <section className="page-section problem-detail">
      <div className="page-heading">
        <Space direction="vertical" size={4}>
          <Link to="/problems">
            <ArrowLeftOutlined /> 返回题库
          </Link>
          <Typography.Title level={2}>
            {data.frontend_id}. {data.translated_title || data.title}
          </Typography.Title>
          <Space wrap>
            <Tag color={difficultyColor(data.difficulty)}>{data.difficulty}</Tag>
            {data.tags.map((tag) => (
              <Tag key={tag.slug}>{tag.translated_name || tag.name || tag.slug}</Tag>
            ))}
          </Space>
        </Space>
        <Button
          href={data.leetcode_url}
          target="_blank"
          rel="noreferrer"
          icon={<LinkOutlined />}
        >
          LeetCode
        </Button>
      </div>

      <Descriptions
        className="problem-meta"
        bordered
        size="small"
        column={{ xs: 1, sm: 1, md: 2 }}
        items={[
          { key: 'title', label: '英文标题', children: data.title },
          {
            key: 'categories',
            label: '分类',
            children:
              data.categories.map((category) => category.name).join('、') || '未分类',
          },
        ]}
      />

      <StatementMarkdown markdown={data.statement_md} />
    </section>
  )
}
