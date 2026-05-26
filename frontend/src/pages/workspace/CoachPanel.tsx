import { Alert, Button, Input, Space, Tag, Typography, message as toast } from 'antd'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import {
  sendPracticeMessage,
  submitLeetCodeFeedback,
  type SubmissionFeedbackResponse,
  type SubmissionResult,
  type UserIntent,
} from '../../api/practice'
import { useLlmRun } from '../../hooks/useLlmRun'
import { CodeAttemptDrawer } from './CodeAttemptDrawer'
import { SubmissionFeedbackModal } from './SubmissionFeedbackModal'
import type { WorkspacePracticeSession } from './types'

type CoachPanelProps = {
  session: WorkspacePracticeSession
  onSessionRefresh: () => void
}

const REQUEST_HINT_MESSAGE = '我需要一个提示。'
const submissionResultLabels: Record<SubmissionResult, string> = {
  ac: 'AC',
  wa: 'WA',
  tle: 'TLE',
  re: 'RE',
  mle: 'MLE',
  ce: 'CE',
  unknown: 'UNKNOWN',
}

type PendingUserMessage = {
  clientId: string
  eventId: number | null
  contentMd: string
}

type TimelineMessage = {
  key: string
  role: 'assistant' | 'user'
  contentMd: string
}

function CoachMarkdown({ markdown }: { markdown: string }) {
  return (
    <div className="coach-chat-content coach-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeSanitize]}
        components={{
          a: ({ href, title, children }) => (
            <a href={href} title={title} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  )
}

export function CoachPanel({
  session,
  onSessionRefresh,
}: CoachPanelProps) {
  const [content, setContent] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [pendingUserMessages, setPendingUserMessages] = useState<PendingUserMessage[]>([])
  const [attemptDrawerOpen, setAttemptDrawerOpen] = useState(false)
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false)
  const [isMarkingAccepted, setIsMarkingAccepted] = useState(false)
  const llmRun = useLlmRun({ onResult: onSessionRefresh })
  const runStatusText = llmRun.isRunning && llmRun.stage ? llmRun.stage : ''
  const codeAttempts = session.code_attempts ?? []
  const submissionFeedbacks = session.submission_feedbacks ?? []
  const latestAttemptSnapshotId =
    codeAttempts.length > 0
      ? codeAttempts[codeAttempts.length - 1].snapshot_id
      : null
  const acceptedCodeSnapshotId = latestAttemptSnapshotId
  const chatEvents = session.events.filter((event) => {
    if (!event.content_md.trim()) {
      return false
    }
    return event.event_type === 'user_message' || event.event_type === 'assistant_message'
  })
  const persistedEventIds = new Set(chatEvents.map((event) => event.id))
  const runningCoachText = llmRun.isRunning
    ? llmRun.displayText.trim() || (runStatusText === 'queued' ? '教练正在处理' : runStatusText)
    : ''
  const timelineMessages: TimelineMessage[] = [
    ...chatEvents.map((event) => ({
      key: `event-${event.id}`,
      role: event.role === 'user' ? ('user' as const) : ('assistant' as const),
      contentMd: event.content_md,
    })),
    ...pendingUserMessages
      .filter((message) => message.eventId === null || !persistedEventIds.has(message.eventId))
      .map((message) => ({
        key: message.clientId,
        role: 'user' as const,
        contentMd: message.contentMd,
      })),
  ]
  if (runningCoachText) {
    timelineMessages.push({
      key: `assistant-running-${llmRun.runId ?? 'pending'}`,
      role: 'assistant',
      contentMd: runningCoachText,
    })
  }

  async function sendCoachMessage(messageIntent: UserIntent, messageContent: string) {
    const trimmedContent = messageContent.trim()
    if (!trimmedContent) {
      return
    }
    const pendingMessage: PendingUserMessage = {
      clientId: `pending-user-${Date.now()}`,
      eventId: null,
      contentMd: trimmedContent,
    }
    setPendingUserMessages((current) => [...current, pendingMessage])
    setContent('')
    setIsSending(true)
    let messageSaved = false
    try {
      const createdMessage = await sendPracticeMessage(session.id, {
        intent: messageIntent,
        content_md: trimmedContent,
        requested_hint_level: null,
      })
      messageSaved = true
      setPendingUserMessages((current) =>
        current.map((message) =>
          message.clientId === pendingMessage.clientId
            ? { ...message, eventId: createdMessage.event_id }
            : message,
        ),
      )
      await llmRun.startRun('coach_turn', {
        session_id: session.id,
        user_event_id: createdMessage.event_id,
        trigger: messageIntent,
      })
    } catch {
      if (!messageSaved) {
        setPendingUserMessages((current) =>
          current.filter((message) => message.clientId !== pendingMessage.clientId),
        )
        setContent(trimmedContent)
      }
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

  async function handleNonAcFeedbackSubmitted(feedback: SubmissionFeedbackResponse) {
    onSessionRefresh()
    try {
      await llmRun.startRun('coach_turn', {
        session_id: session.id,
        user_event_id: feedback.event_id,
        trigger: 'submit_feedback',
      })
    } catch {
      toast.error('提交结果已保存，教练分析启动失败，请稍后重试')
    }
  }

  return (
    <div className="workspace-pane coach-panel">
      <div className="workspace-pane-heading">
        <h3>教练</h3>
        <Space wrap>
          <Button onClick={() => setAttemptDrawerOpen(true)}>代码尝试记录</Button>
          <Button onClick={() => setFeedbackModalOpen(true)}>回填未通过结果</Button>
          <Button
            type="primary"
            onClick={handleAccepted}
            loading={isMarkingAccepted || llmRun.isRunning}
          >
            LeetCode 已 AC
          </Button>
        </Space>
      </div>

      <section className="coach-chat-timeline" aria-label="教练聊天记录">
        {timelineMessages.length === 0 ? (
          <Typography.Text type="secondary">暂无训练消息</Typography.Text>
        ) : (
          timelineMessages.map((message) => (
            <div
              className={`coach-chat-message coach-chat-message-${message.role}`}
              key={message.key}
            >
              <Typography.Text className="coach-message-role">
                {message.role === 'assistant' ? '教练' : '我'}
              </Typography.Text>
              <CoachMarkdown markdown={message.contentMd} />
            </div>
          ))
        )}
      </section>

      <section className="coach-section">
        {submissionFeedbacks.length > 0 ? (
          <div className="coach-feedback-history">
            <Typography.Text strong>提交反馈历史</Typography.Text>
            <div className="coach-feedback-list">
              {submissionFeedbacks.map((feedback) => (
                <article className="coach-feedback-item" key={feedback.id}>
                  <Space wrap>
                    <Tag>{submissionResultLabels[feedback.result]}</Tag>
                    {feedback.code_snapshot_id ? (
                      <Typography.Text type="secondary">
                        {`代码快照 #${feedback.code_snapshot_id}`}
                      </Typography.Text>
                    ) : null}
                  </Space>
                  {feedback.failed_case_text ? (
                    <Typography.Paragraph className="coach-feedback-text">
                      {feedback.failed_case_text}
                    </Typography.Paragraph>
                  ) : null}
                  {feedback.error_message ? (
                    <Typography.Paragraph className="coach-feedback-text" type="secondary">
                      {feedback.error_message}
                    </Typography.Paragraph>
                  ) : null}
                  {feedback.note_md ? (
                    <Typography.Paragraph className="coach-feedback-text">
                      {feedback.note_md}
                    </Typography.Paragraph>
                  ) : null}
                </article>
              ))}
            </div>
          </div>
        ) : null}
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
            {llmRun.isRunning ? (
              <Button aria-label="取消" onClick={llmRun.cancelRun}>
                取消
              </Button>
            ) : null}
            {runStatusText ? (
              <Typography.Text type="secondary" className="coach-run-status-text">
                {runStatusText}
              </Typography.Text>
            ) : null}
          </Space>
          {llmRun.error ? (
            <Alert showIcon type="error" message={llmRun.error.message} />
          ) : null}
        </div>
      </section>

      <CodeAttemptDrawer
        open={attemptDrawerOpen}
        attempts={codeAttempts}
        onClose={() => setAttemptDrawerOpen(false)}
      />
      <SubmissionFeedbackModal
        codeSnapshotId={latestAttemptSnapshotId}
        onClose={() => setFeedbackModalOpen(false)}
        onSubmitted={handleNonAcFeedbackSubmitted}
        open={feedbackModalOpen}
        sessionId={session.id}
      />
    </div>
  )
}
