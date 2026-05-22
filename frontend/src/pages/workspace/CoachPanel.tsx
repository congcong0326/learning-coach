import { Alert, Button, Input, Select, Space, Tag, Typography, message as toast } from 'antd'
import { useState } from 'react'

import {
  sendPracticeMessage,
  type HintLevel,
  type UserIntent,
} from '../../api/practice'
import { useLlmRun } from '../../hooks/useLlmRun'
import { hintLevelLabel, phaseLabel } from './coachDisplay'
import { SubmissionFeedbackModal } from './SubmissionFeedbackModal'
import type { WorkspacePracticeSession } from './types'

type CoachPanelProps = {
  session: WorkspacePracticeSession
  onSessionRefresh: () => void
}

const intentOptions: Array<{ label: string; value: UserIntent }> = [
  { label: '描述思路', value: 'describe_idea' },
  { label: '我卡住了', value: 'stuck' },
  { label: '请求提示', value: 'request_hint' },
  { label: '代码 Review', value: 'code_review' },
  { label: '提交反馈', value: 'submit_feedback' },
  { label: '请求复盘', value: 'request_summary' },
]

const hintOptions: Array<{ label: string; value: HintLevel }> = [
  { label: hintLevelLabel('questioning'), value: 'questioning' },
  { label: hintLevelLabel('direction'), value: 'direction' },
  { label: hintLevelLabel('key_hint'), value: 'key_hint' },
  { label: hintLevelLabel('reflection'), value: 'reflection' },
]

export function CoachPanel({ session, onSessionRefresh }: CoachPanelProps) {
  const [intent, setIntent] = useState<UserIntent>('describe_idea')
  const [requestedHintLevel, setRequestedHintLevel] = useState<HintLevel>(
    session.visible_hint_gear,
  )
  const [content, setContent] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const llmRun = useLlmRun({ onResult: onSessionRefresh })
  const profile = session.profile_snapshot

  async function handleSend() {
    const trimmedContent = content.trim()
    if (!trimmedContent) {
      return
    }
    setIsSending(true)
    try {
      const createdMessage = await sendPracticeMessage(session.id, {
        intent,
        content_md: trimmedContent,
        requested_hint_level: intent === 'request_hint' ? requestedHintLevel : null,
      })
      setContent('')
      await llmRun.startRun('coach_turn', {
        session_id: session.id,
        user_event_id: createdMessage.event_id,
        trigger: intent,
      })
    } catch {
      toast.error('消息发送失败，请稍后重试')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="workspace-pane coach-panel">
      <div className="workspace-pane-heading">
        <h3>教练</h3>
        <Button onClick={() => setFeedbackOpen(true)}>提交回填</Button>
      </div>

      <div className="coach-state-bar">
        <Tag color="processing">{phaseLabel(session.phase)}</Tag>
        <Tag>{session.status}</Tag>
        <Tag>{hintLevelLabel(session.visible_hint_gear)}</Tag>
      </div>

      <section className="coach-section">
        <Typography.Text strong>画像快照</Typography.Text>
        <div className="coach-profile-grid">
          <span>画像来源</span>
          <Typography.Text>{profile.source}</Typography.Text>
          <span>置信度</span>
          <Typography.Text>{profile.confidence}</Typography.Text>
          <span>水平</span>
          <Typography.Text>{profile.overall_level}</Typography.Text>
          <span>训练偏好</span>
          <Typography.Text>{profile.preferred_training_mode}</Typography.Text>
        </div>
        {profile.recent_summary ? (
          <Typography.Paragraph className="coach-summary">
            {profile.recent_summary}
          </Typography.Paragraph>
        ) : null}
      </section>

      <section className="coach-section">
        <Typography.Text strong>事件时间线</Typography.Text>
        <div className="coach-timeline">
          {session.events.length === 0 ? (
            <Typography.Text type="secondary">暂无训练事件</Typography.Text>
          ) : (
            session.events.map((event) => (
              <div className="coach-timeline-item" key={event.id}>
                <Space wrap size={6}>
                  <Tag>{event.role}</Tag>
                  <Tag>{phaseLabel(event.phase)}</Tag>
                  {event.visible_hint_gear ? (
                    <Tag>{hintLevelLabel(event.visible_hint_gear)}</Tag>
                  ) : null}
                </Space>
                <Typography.Paragraph className="coach-event-content">
                  {event.content_md}
                </Typography.Paragraph>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="coach-section">
        <div className="coach-message-box">
          <Space wrap>
            <Select
              aria-label="消息意图"
              value={intent}
              options={intentOptions}
              onChange={setIntent}
              style={{ width: 132 }}
            />
            <Select
              aria-label="提示档位"
              value={requestedHintLevel}
              options={hintOptions}
              onChange={setRequestedHintLevel}
              style={{ width: 132 }}
            />
          </Space>
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
            {llmRun.isRunning ? <Button onClick={llmRun.cancelRun}>取消</Button> : null}
            {llmRun.stage ? (
              <Typography.Text type="secondary">状态 {llmRun.stage}</Typography.Text>
            ) : null}
          </Space>
          {llmRun.error ? (
            <Alert showIcon type="error" message={llmRun.error.message} />
          ) : null}
          {llmRun.displayText ? (
            <div className="coach-run-output">{llmRun.displayText}</div>
          ) : null}
        </div>
      </section>

      <SubmissionFeedbackModal
        open={feedbackOpen}
        sessionId={session.id}
        onClose={() => setFeedbackOpen(false)}
        onSubmitted={onSessionRefresh}
      />
    </div>
  )
}
