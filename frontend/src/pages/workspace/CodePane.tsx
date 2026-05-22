import { Button, Input, Select, Space, Typography, message } from 'antd'
import { useMemo, useState } from 'react'

import { saveCodeSnapshot, type CodeSnapshotPayload } from '../../api/practice'

type CodePaneProps = {
  sessionId?: number
  initialCode?: string
  onSnapshotSaved?: (snapshotId: number) => void
}

const languageOptions: Array<{ label: string; value: CodeSnapshotPayload['language'] }> = [
  { label: 'Python 3', value: 'python3' },
  { label: 'JavaScript', value: 'javascript' },
  { label: 'Java', value: 'java' },
  { label: 'Go', value: 'go' },
  { label: 'C', value: 'c' },
]

export function CodePane({ sessionId, initialCode = '', onSnapshotSaved }: CodePaneProps) {
  const [language, setLanguage] = useState<CodeSnapshotPayload['language']>('python3')
  const [codeText, setCodeText] = useState(initialCode)
  const [clientRevision, setClientRevision] = useState(1)
  const [isSaving, setIsSaving] = useState(false)
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null)
  const canSave = Boolean(sessionId) && codeText.trim().length > 0

  const selectedLanguage = useMemo(
    () => languageOptions.find((option) => option.value === language)?.label ?? language,
    [language],
  )

  async function handleSave() {
    if (!sessionId || !canSave) {
      return
    }
    setIsSaving(true)
    try {
      const snapshot = await saveCodeSnapshot(sessionId, {
        language,
        code_text: codeText,
        source: 'manual_save',
        client_revision: clientRevision,
      })
      setClientRevision((current) => current + 1)
      setLastSavedAt(new Date(snapshot.created_at).toLocaleString())
      onSnapshotSaved?.(snapshot.id)
      message.success('代码快照已保存')
    } catch {
      message.error('保存失败，代码草稿已保留')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="workspace-pane code-pane">
      <div className="workspace-pane-heading">
        <h3>代码</h3>
        <Typography.Text type="secondary">{selectedLanguage}</Typography.Text>
      </div>
      <Space className="code-pane-actions" wrap>
        <Select
          aria-label="选择语言"
          value={language}
          options={languageOptions}
          onChange={setLanguage}
          style={{ width: 140 }}
        />
        <Button type="primary" onClick={handleSave} loading={isSaving} disabled={!canSave}>
          保存快照
        </Button>
        {lastSavedAt ? (
          <Typography.Text type="secondary">上次保存 {lastSavedAt}</Typography.Text>
        ) : null}
      </Space>
      <Input.TextArea
        aria-label="代码草稿"
        className="code-draft-input"
        value={codeText}
        onChange={(event) => {
          setCodeText(event.target.value)
        }}
        placeholder="在这里记录当前解法代码。保存失败不会清空草稿。"
        rows={18}
      />
    </div>
  )
}
