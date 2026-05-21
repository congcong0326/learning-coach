import { Alert, Button, Space, Spin, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'

import type { LlmRunStatus } from '../api/llmRuns'

type LlmStreamingPanelError =
  | string
  | {
      message?: string | null
      code?: string | null
    }
  | null
  | undefined

type LlmStreamingPanelProps = {
  title: string
  status: LlmRunStatus | 'idle'
  stage: string
  displayText: string
  error: LlmStreamingPanelError
  onCancel: () => void
  children?: ReactNode
}

type PanelStatus = LlmStreamingPanelProps['status']

const activeStatuses: PanelStatus[] = ['pending', 'running']

const statusLabels: Record<PanelStatus, string> = {
  idle: '未开始',
  pending: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '失败',
  canceled: '已取消',
}

const statusColors: Partial<Record<PanelStatus, string>> = {
  pending: 'processing',
  running: 'processing',
  succeeded: 'success',
  failed: 'error',
  canceled: 'default',
  idle: 'default',
}

function getErrorMessage(error: LlmStreamingPanelError) {
  if (!error) {
    return ''
  }
  if (typeof error === 'string') {
    return error
  }
  return error.message ?? 'LLM 生成失败，请稍后重试。'
}

export function LlmStreamingPanel({
  title,
  status,
  stage,
  displayText,
  error,
  onCancel,
  children,
}: LlmStreamingPanelProps) {
  const isActive = activeStatuses.includes(status)
  const errorMessage = getErrorMessage(error)

  return (
    <section className="workflow-panel" aria-label={title}>
      <Space align="center" size={10} wrap>
        {isActive ? <Spin size="small" /> : null}
        <Typography.Title level={3}>{title}</Typography.Title>
        <Tag color={statusColors[status]}>
          {statusLabels[status]}
        </Tag>
      </Space>

      <Space align="center" size={8} wrap>
        <Typography.Text type="secondary">进度</Typography.Text>
        <Typography.Text>{stage || statusLabels[status]}</Typography.Text>
      </Space>

      {displayText ? (
        <Typography.Paragraph
          style={{
            margin: 0,
            overflowWrap: 'anywhere',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {displayText}
        </Typography.Paragraph>
      ) : null}

      {errorMessage ? (
        <Alert showIcon type="error" title="生成失败" description={errorMessage} />
      ) : null}

      {children}

      {isActive ? (
        <div>
          <Button onClick={onCancel}>取消生成</Button>
        </div>
      ) : null}
    </section>
  )
}
