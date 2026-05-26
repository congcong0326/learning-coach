import { Alert, Button, Input, Space, Typography, message as toast } from 'antd'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import {
  sendPracticeMessage,
  submitLeetCodeFeedback,
  type UserIntent,
} from '../../api/practice'
import { useLlmRun } from '../../hooks/useLlmRun'
import { CodeAttemptDrawer } from './CodeAttemptDrawer'
import type { WorkspacePracticeSession } from './types'

type CoachPanelProps = {
  session: WorkspacePracticeSession
  onSessionRefresh: () => void
}

const REQUEST_HINT_MESSAGE = '我需要一个提示。'
const SUMMARY_PENDING_MESSAGE = 'AC 已记录，正在生成单题复盘。'
const DEFAULT_RUNNING_MESSAGE = '教练正在处理'
const SUMMARY_RUNNING_MESSAGE = '正在生成单题复盘'

type ActiveRunPurpose = 'turn' | 'summary' | null

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

type ElapsedState = {
  startedAtMs: number | null
  seconds: number
}

function useRunElapsedSeconds(isRunning: boolean, startedAtMs: number | null) {
  const [elapsedState, setElapsedState] = useState<ElapsedState>({
    startedAtMs: null,
    seconds: 0,
  })

  useEffect(() => {
    if (!isRunning) {
      return undefined
    }

    const effectiveStartedAtMs = startedAtMs ?? Date.now()
    const timer = window.setInterval(() => {
      setElapsedState({
        startedAtMs: effectiveStartedAtMs,
        seconds: Math.max(0, Math.floor((Date.now() - effectiveStartedAtMs) / 1000)),
      })
    }, 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [isRunning, startedAtMs])

  if (!isRunning) {
    return 0
  }
  if (startedAtMs !== null && elapsedState.startedAtMs !== startedAtMs) {
    return 0
  }
  return elapsedState.seconds
}

function formatElapsedTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function hasAcceptedResult(session: WorkspacePracticeSession) {
  return (
    session.final_result === 'ac' ||
    (session.submission_feedbacks ?? []).some((feedback) => feedback.result === 'ac')
  )
}

function readableRunStage(stage: string, fallback: string) {
  const normalizedStage = stage.trim()
  if (!normalizedStage || normalizedStage === 'queued' || normalizedStage === 'pending') {
    return fallback
  }
  return normalizedStage
}

export function CoachPanel({
  session,
  onSessionRefresh,
}: CoachPanelProps) {
  const [content, setContent] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [pendingUserMessages, setPendingUserMessages] = useState<PendingUserMessage[]>([])
  const [attemptDrawerOpen, setAttemptDrawerOpen] = useState(false)
  const [isMarkingAccepted, setIsMarkingAccepted] = useState(false)
  const [localAcceptedSessionId, setLocalAcceptedSessionId] = useState<number | null>(null)
  const [activeRunPurpose, setActiveRunPurpose] = useState<ActiveRunPurpose>(null)
  const [runStartedAtMs, setRunStartedAtMs] = useState<number | null>(null)
  const llmRun = useLlmRun({
    onResult: () => {
      setRunStartedAtMs(null)
      onSessionRefresh()
    },
  })
  const elapsedSeconds = useRunElapsedSeconds(llmRun.isRunning, runStartedAtMs)
  const acceptedResult = localAcceptedSessionId === session.id || hasAcceptedResult(session)
  const isSummaryRunContext =
    activeRunPurpose === 'summary' ||
    (activeRunPurpose === null && llmRun.isRunning && acceptedResult)
  const runStageText = llmRun.isRunning
    ? readableRunStage(
        llmRun.stage,
        isSummaryRunContext ? SUMMARY_RUNNING_MESSAGE : DEFAULT_RUNNING_MESSAGE,
      )
    : ''
  const runStatusText = runStageText
    ? `${runStageText} · 已等待 ${formatElapsedTime(elapsedSeconds)}`
    : ''
  const codeAttempts = session.code_attempts ?? []
  const latestAttemptSnapshotId =
    codeAttempts.length > 0
      ? codeAttempts[codeAttempts.length - 1].snapshot_id
      : null
  const acceptedCodeSnapshotId = latestAttemptSnapshotId
  const acceptedButtonText = acceptedResult ? '已记录 AC' : 'LeetCode 已 AC'
  const chatEvents = session.events.filter((event) => {
    if (!event.content_md.trim()) {
      return false
    }
    return event.event_type === 'user_message' || event.event_type === 'assistant_message'
  })
  const persistedEventIds = new Set(chatEvents.map((event) => event.id))
  const runningCoachText = llmRun.isRunning
    ? llmRun.displayText.trim() ||
      (isSummaryRunContext ? SUMMARY_PENDING_MESSAGE : runStageText)
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
      setActiveRunPurpose('turn')
      setRunStartedAtMs(Date.now())
      await llmRun.startRun('coach_turn', {
        session_id: session.id,
        user_event_id: createdMessage.event_id,
        trigger: messageIntent,
      })
    } catch {
      setActiveRunPurpose(null)
      setRunStartedAtMs(null)
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
    if (acceptedResult) {
      return
    }
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

      setLocalAcceptedSessionId(session.id)
      onSessionRefresh()
      try {
        setActiveRunPurpose('summary')
        setRunStartedAtMs(Date.now())
        await llmRun.startRun('coach_summary', {
          session_id: session.id,
          trigger: 'request_summary',
        })
      } catch {
        setActiveRunPurpose(null)
        setRunStartedAtMs(null)
        toast.error('AC 已记录，复盘生成失败，请稍后重试')
      }
    } finally {
      setIsMarkingAccepted(false)
    }
  }

  async function handleCancelRun() {
    setRunStartedAtMs(null)
    await llmRun.cancelRun()
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
            loading={
              isMarkingAccepted || (activeRunPurpose === 'summary' && llmRun.isRunning)
            }
            disabled={acceptedResult || isSending || llmRun.isRunning}
          >
            {acceptedButtonText}
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
        <div className="coach-message-box">
          <Input.TextArea
            aria-label="发送给教练"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="粘贴你的思路、代码、LeetCode 报错或失败用例，教练会判断下一步"
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
              <Button aria-label="取消" onClick={handleCancelRun}>
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
    </div>
  )
}
