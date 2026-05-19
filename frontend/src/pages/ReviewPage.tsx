import { Descriptions, Typography } from 'antd'

export function ReviewPage() {
  return (
    <section className="page-section">
      <Typography.Title level={2}>复盘</Typography.Title>
      <Descriptions
        bordered
        size="middle"
        column={1}
        items={[
          { key: 'result', label: '最终结果', children: '-' },
          { key: 'hint', label: '最高提示等级', children: '-' },
          { key: 'profile', label: '画像更新', children: '-' },
        ]}
      />
    </section>
  )
}
