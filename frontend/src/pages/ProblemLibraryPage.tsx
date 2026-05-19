import { Table, Tag, Typography } from 'antd'

const rows = [
  {
    key: 'two-sum',
    id: 1,
    title: 'Two Sum',
    difficulty: 'Easy',
    status: '未开始',
  },
]

export function ProblemLibraryPage() {
  return (
    <section className="page-section">
      <div className="page-heading">
        <Typography.Title level={2}>题库列表</Typography.Title>
        <Tag color="default">foundation</Tag>
      </div>
      <Table
        rowKey="key"
        size="middle"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: '题号', dataIndex: 'id', width: 88 },
          { title: '标题', dataIndex: 'title' },
          { title: '难度', dataIndex: 'difficulty', width: 120 },
          { title: '状态', dataIndex: 'status', width: 120 },
        ]}
      />
    </section>
  )
}
