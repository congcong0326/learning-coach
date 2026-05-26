import {
  CheckCircleFilled,
  CloseCircleFilled,
  DownOutlined,
  ExclamationCircleOutlined,
  MinusCircleFilled,
  RightOutlined,
} from '@ant-design/icons'
import { Button, Empty, Modal, Space, Tag, Tooltip, Typography } from 'antd'
import { useState, type ReactElement } from 'react'

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
  const [expandedSnapshotIds, setExpandedSnapshotIds] = useState<Set<number>>(new Set())

  function toggleExpanded(snapshotId: number) {
    setExpandedSnapshotIds((current) => {
      const next = new Set(current)
      if (next.has(snapshotId)) {
        next.delete(snapshotId)
      } else {
        next.add(snapshotId)
      }
      return next
    })
  }

  function resetExpanded() {
    setExpandedSnapshotIds(new Set())
  }

  function handleClose() {
    resetExpanded()
    onClose()
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      resetExpanded()
    }
  }

  return (
    <Modal
      centered
      className="code-attempt-modal"
      destroyOnHidden
      footer={null}
      afterOpenChange={handleOpenChange}
      onCancel={handleClose}
      open={open}
      title="代码尝试记录"
      width={760}
    >
      {attempts.length === 0 ? (
        <Empty description="暂无代码尝试记录" />
      ) : (
        <div className="code-attempt-list">
          {attempts.map((attempt, index) => {
            const meta = statusMeta[attempt.quality_status]
            const isExpanded = expandedSnapshotIds.has(attempt.snapshot_id)
            return (
              <article className="code-attempt-item" key={attempt.snapshot_id}>
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
                  <Button
                    aria-expanded={isExpanded}
                    className="code-attempt-toggle"
                    icon={
                      isExpanded ? (
                        <DownOutlined aria-hidden="true" />
                      ) : (
                        <RightOutlined aria-hidden="true" />
                      )
                    }
                    onClick={() => toggleExpanded(attempt.snapshot_id)}
                    type="text"
                  >
                    完整代码
                  </Button>
                  {isExpanded ? (
                    <pre className="code-attempt-code">{attempt.code_text}</pre>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
