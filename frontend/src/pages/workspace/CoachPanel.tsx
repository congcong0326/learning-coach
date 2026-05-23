import { Alert, Button, Input, Space, Tag, Typography, message as toast } from 'antd'
import { useState } from 'react'

import {
  sendPracticeMessage,
  submitLeetCodeFeedback,
  type UserIntent,
} from '../../api/practice'
import { useLlmRun } from '../../hooks/useLlmRun'
import { CodeAttemptDrawer } from './CodeAttemptDrawer'
import { hintLevelLabel, phaseLabel } from './coachDisplay'
import type { WorkspacePracticeSession } from './types'

type CoachPanelProps = {
  session: WorkspacePracticeSession
  codeSnapshotId?: number | null
  onSessionRefresh: () => void
}

const REQUEST_HINT_MESSAGE = '我需要一个提示。'

export function CoachPanel({
  session,
  codeSnapshotId = null,
  onSessionRefresh,
}: CoachPanelProps) {
  const [content, setContent] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [attemptDrawerOpen, setAttemptDrawerOpen] = useState(false)
  const [isMarkingAccepted, setIsMarkingAccepted] = useState(false)
  const llmRun = useLlmRun({ onResult: onSessionRefresh })
  const shouldShowRunOutput = llmRun.isRunning && Boolean(llmRun.displayText.trim())
  const codeAttempts = session.code_attempts ?? []
  const latestAttemptSnapshotId =
    codeAttempts.length > 0
      ? codeAttempts[codeAttempts.length - 1].snapshot_id
      : null
  const acceptedCodeSnapshotId = codeSnapshotId ?? latestAttemptSnapshotId

  async function sendCoachMessage(messageIntent: UserIntent, messageContent: string) {
    const trimmedContent = messageContent.trim()
    if (!trimmedContent) {
      return
    }
    setIsSending(true)
    try {
      const createdMessage = await sendPracticeMessage(session.id, {
        intent: messageIntent,
        content_md: trimmedContent,
        requested_hint_level: null,
      })
      setContent('')
      await llmRun.startRun('coach_turn', {
        session_id: session.id,
        user_event_id: createdMessage.event_id,
        trigger: messageIntent,
      })
    } catch {
      toast.error('消息发送失败，请稍后重试')
    } finally {
      setIsSending(false)
    }
  }

  async function handleSend() {
    await sendCoachMessage('unknown', content)
  }

  async function handleRequestHint() {
    await sendCoachMessage('request_hint', content.trim() || REQUEST_HINT_MESSAGE)
  }

  async function handleAccepted() {
    setIsMarkingAccepted(true)
    try {
      try {
        await submitLeetCodeFeedback(session.id, {
          result: 'ac',
          code_snapshot_id: acceptedCodeSnapshotId,
        })
      } catch {
        toast.error('AC 状态记录失败，请稍后重试')
        return
      }

      onSessionRefresh()
      try {
        await llmRun.startRun('coach_summary', {
          session_id: session.id,
          trigger: 'request_summary',
        })
      } catch {
        toast.error('AC 已记录，复盘生成失败，请稍后重试')
      }
    } finally {
      setIsMarkingAccepted(false)
    }
  }

  return (
    <div className="workspace-pane coach-panel">
      <div className="workspace-pane-heading">
        <h3>教练</h3>
        <Space wrap>
          <Button onClick={() => setAttemptDrawerOpen(true)}>代码尝试记录</Button>
          <Button
            type="primary"
            onClick={handleAccepted}
            loading={isMarkingAccepted || llmRun.isRunning}
          >
            LeetCode 已 AC
          </Button>
        </Space>
      </div>

      <div className="coach-state-bar">
        <Tag color="processing">{phaseLabel(session.phase)}</Tag>
        <Tag>{session.status}</Tag>
        <Tag>{hintLevelLabel(session.visible_hint_gear)}</Tag>
      </div>

      <section className="coach-chat-timeline" aria-label="教练聊天记录">
        {session.events.length === 0 ? (
          <Typography.Text type="secondary">暂无训练消息</Typography.Text>
        ) : (
          session.events.map((event) => (
            <div
              className={`coach-chat-message coach-chat-message-${event.role}`}
              key={event.id}
            >
              <Space wrap size={6}>
                <Tag>
                  {event.role === 'assistant'
                    ? '教练'
                    : event.role === 'user'
                      ? '我'
                      : '系统'}
                </Tag>
                <Tag>{phaseLabel(event.phase)}</Tag>
                {event.visible_hint_gear ? (
                  <Tag>{hintLevelLabel(event.visible_hint_gear)}</Tag>
                ) : null}
              </Space>
              {event.content_md ? (
                <Typography.Paragraph className="coach-chat-content">
                  {event.content_md}
                </Typography.Paragraph>
              ) : (
                <Typography.Text type="secondary">
                  {event.event_type === 'code_saved'
                    ? '已记录一次代码尝试'
                    : event.event_type === 'submission_feedback'
                      ? '已记录 LeetCode 结果'
                      : event.event_type}
                </Typography.Text>
              )}
            </div>
          ))
        )}
      </section>

      <section className="coach-section">
        <div className="coach-message-box">
          <Input.TextArea
            aria-label="发送给教练"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="描述你的思路、卡点、代码问题或 LeetCode 结果"
            rows={4}
          />
          <Space wrap>
            <Button
              type="primary"
              onClick={handleSend}
              loading={isSending || llmRun.isRunning}
              disabled={!content.trim()}
            >
              发送
            </Button>
            <Button onClick={handleRequestHint} disabled={isSending || llmRun.isRunning}>
              请求提示
            </Button>
            {llmRun.isRunning ? <Button onClick={llmRun.cancelRun}>取消</Button> : null}
            {llmRun.isRunning && llmRun.stage ? (
              <Typography.Text type="secondary">状态 {llmRun.stage}</Typography.Text>
            ) : null}
          </Space>
          {llmRun.error ? (
            <Alert showIcon type="error" message={llmRun.error.message} />
          ) : null}
          {shouldShowRunOutput ? (
            <div className="coach-run-output">{llmRun.displayText}</div>
          ) : null}
        </div>
      </section>

      <CodeAttemptDrawer
        open={attemptDrawerOpen}
        attempts={codeAttempts}
        onClose={() => setAttemptDrawerOpen(false)}
      />
    </div>
  )
}
