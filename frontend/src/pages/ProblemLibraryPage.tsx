import { useQuery } from '@tanstack/react-query'
import { Alert, Space, Table, Tag, Typography } from 'antd'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { getProblems, type ProblemListItem } from '../api/problems'

function difficultyColor(difficulty: ProblemListItem['difficulty']) {
  if (difficulty === 'Easy') {
    return 'success'
  }
  if (difficulty === 'Medium') {
    return 'warning'
  }
  return 'error'
}

export function ProblemLibraryPage() {
  const [page, setPage] = useState(1)
  const pageSize = 20
  const { data, isError, isLoading } = useQuery({
    queryKey: ['problems', page, pageSize],
    queryFn: () => getProblems({ page, page_size: pageSize }),
  })

  return (
    <section className="page-section">
      <div className="page-heading">
        <Typography.Title level={2}>题库列表</Typography.Title>
        <Tag color="default">{data?.total ?? 0} 题</Tag>
      </div>

      {isError ? (
        <Alert
          showIcon
          type="error"
          message="题库加载失败"
          className="page-alert"
        />
      ) : null}

      <Table
        rowKey="slug"
        size="middle"
        loading={isLoading}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? pageSize,
          total: data?.total ?? 0,
          showSizeChanger: false,
          onChange: (nextPage) => {
            setPage(nextPage)
          },
        }}
        dataSource={data?.items ?? []}
        columns={[
          { title: '题号', dataIndex: 'frontend_id', width: 88 },
          {
            title: '标题',
            key: 'title',
            render: (_, row: ProblemListItem) => (
              <Link to={`/workspace/${row.slug}`}>
                <Space direction="vertical" size={0}>
                  <span>{row.title}</span>
                  <Typography.Text type="secondary">
                    {row.translated_title}
                  </Typography.Text>
                </Space>
              </Link>
            ),
          },
          {
            title: '难度',
            dataIndex: 'difficulty',
            width: 120,
            render: (difficulty: ProblemListItem['difficulty']) => (
              <Tag color={difficultyColor(difficulty)}>{difficulty}</Tag>
            ),
          },
          {
            title: '标签',
            key: 'tags',
            render: (_, row: ProblemListItem) => (
              <div className="problem-tags">
                {row.tags.map((tag) => (
                  <Tag key={tag.slug}>
                    {tag.translated_name || tag.name || tag.slug}
                  </Tag>
                ))}
              </div>
            ),
          },
          {
            title: '分类',
            key: 'categories',
            width: 180,
            render: (_, row: ProblemListItem) => (
              <div className="problem-tags">
                {row.categories.map((category) => (
                  <Tag key={category.slug} color="blue">
                    {category.name}
                  </Tag>
                ))}
              </div>
            ),
          },
        ]}
      />
    </section>
  )
}
