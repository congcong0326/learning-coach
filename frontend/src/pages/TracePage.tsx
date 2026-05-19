import { Table, Typography } from 'antd'

export function TracePage() {
  return (
    <section className="page-section">
      <Typography.Title level={2}>Trace</Typography.Title>
      <Table
        rowKey="id"
        size="middle"
        pagination={false}
        dataSource={[]}
        columns={[
          { title: '节点', dataIndex: 'nodeName' },
          { title: '阶段', dataIndex: 'phase' },
          { title: '耗时', dataIndex: 'latency' },
        ]}
      />
    </section>
  )
}
