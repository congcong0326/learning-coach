import { Form, Input, InputNumber, Modal, Select, Typography, message } from 'antd'
import { useState } from 'react'

import {
  submitLeetCodeFeedback,
  type SubmissionFeedbackPayload,
  type SubmissionFeedbackResponse,
  type SubmissionResult,
} from '../../api/practice'

type SubmissionFeedbackModalProps = {
  open: boolean
  sessionId: number
  codeSnapshotId?: number | null
  onClose: () => void
  onSubmitted?: (feedback: SubmissionFeedbackResponse) => void | Promise<void>
}

const resultOptions: Array<{ label: string; value: SubmissionResult }> = [
  { label: 'WA', value: 'wa' },
  { label: 'TLE', value: 'tle' },
  { label: 'RE', value: 're' },
  { label: 'MLE', value: 'mle' },
  { label: 'CE', value: 'ce' },
  { label: 'Unknown', value: 'unknown' },
]

export function SubmissionFeedbackModal({
  open,
  sessionId,
  codeSnapshotId = null,
  onClose,
  onSubmitted,
}: SubmissionFeedbackModalProps) {
  const [form] = Form.useForm<SubmissionFeedbackPayload>()
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit() {
    const values = await form.validateFields()
    setIsSubmitting(true)
    try {
      const feedback = await submitLeetCodeFeedback(sessionId, {
        ...values,
        code_snapshot_id: codeSnapshotId,
        runtime_ms: values.runtime_ms ?? null,
        memory_kb: values.memory_kb ?? null,
      })
      message.success('提交结果已回填')
      form.resetFields()
      await onSubmitted?.(feedback)
      onClose()
    } catch {
      message.error('提交回填失败，请稍后重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      title="未通过结果回填"
      open={open}
      okText="保存"
      cancelText="取消"
      confirmLoading={isSubmitting}
      onOk={handleSubmit}
      onCancel={onClose}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        {codeSnapshotId
          ? `将关联代码快照 #${codeSnapshotId}`
          : '未选择代码快照，将尝试关联服务端最近保存的代码快照。'}
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={{ result: 'wa' }}>
        <Form.Item
          name="result"
          label="LeetCode 结果"
          rules={[{ required: true, message: '请选择提交结果' }]}
        >
          <Select options={resultOptions} />
        </Form.Item>
        <Form.Item name="failed_case_text" label="失败用例">
          <Input.TextArea rows={3} placeholder="WA/TLE/RE 时粘贴关键失败用例" />
        </Form.Item>
        <Form.Item name="error_message" label="错误信息">
          <Input.TextArea rows={3} placeholder="编译错误、运行错误或平台提示" />
        </Form.Item>
        <Form.Item name="note_md" label="备注">
          <Input.TextArea rows={3} placeholder="你的初步判断或希望教练重点看的地方" />
        </Form.Item>
        <Form.Item name="runtime_ms" label="运行耗时 ms">
          <InputNumber min={0} precision={0} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="memory_kb" label="内存 KB">
          <InputNumber min={0} precision={0} style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
