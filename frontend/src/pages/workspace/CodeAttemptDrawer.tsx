import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleOutlined,
  MinusCircleFilled,
} from '@ant-design/icons'
import { Drawer, Empty, List, Space, Tag, Tooltip, Typography } from 'antd'
import type { ReactElement } from 'react'

import type { CodeAttempt, CodeAttemptQuality } from '../../api/practice'

type CodeAttemptDrawerProps = {
  open: boolean
  attempts: CodeAttempt[]
  onClose: () => void
}

const statusMeta: Record<
  CodeAttemptQuality,
  { label: string; className: string; icon: ReactElement }
> = {
  pending: {
    label: '待评估',
    className: 'code-attempt-status-pending',
    icon: <MinusCircleFilled aria-hidden="true" />,
  },
  needs_fix: {
    label: '建议修改',
    className: 'code-attempt-status-needs-fix',
    icon: <CloseCircleFilled aria-hidden="true" />,
  },
  ready_to_submit: {
    label: '可尝试提交',
    className: 'code-attempt-status-ready',
    icon: <CheckCircleFilled aria-hidden="true" />,
  },
}

export function CodeAttemptDrawer({
  open,
  attempts,
  onClose,
}: CodeAttemptDrawerProps) {
  return (
    <Drawer title="代码尝试记录" open={open} onClose={onClose} width={520}>
      {attempts.length === 0 ? (
        <Empty description="暂无代码尝试记录" />
      ) : (
        <List
          dataSource={attempts}
          renderItem={(attempt, index) => {
            const meta = statusMeta[attempt.quality_status]
            return (
              <List.Item className="code-attempt-item">
                <div className="code-attempt-row">
                  <Space className="code-attempt-heading" wrap>
                    <Typography.Text strong>{`第 ${index + 1} 次尝试`}</Typography.Text>
                    <Tag className={meta.className} icon={meta.icon}>
                      {meta.label}
                    </Tag>
                    <Typography.Text type="secondary">{attempt.language}</Typography.Text>
                    {attempt.quality_comment ? (
                      <Tooltip title={attempt.quality_comment}>
                        <button
                          aria-label="AI 简评"
                          className="icon-button-plain"
                          type="button"
                        >
                          <ExclamationCircleOutlined aria-hidden="true" />
                        </button>
                      </Tooltip>
                    ) : null}
                  </Space>
                  <pre className="code-attempt-preview">{attempt.code_preview}</pre>
                </div>
              </List.Item>
            )
          }}
        />
      )}
    </Drawer>
  )
}
