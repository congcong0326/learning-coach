import { ApiError } from './client'

export type RestoreDatabaseBackupResult = {
  status: 'ok'
  restored_at: string
  file_size_bytes: number
}

function parseErrorDetail(payload: unknown): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  return 'request_failed'
}

async function raiseForError(response: Response): Promise<void> {
  if (response.ok) {
    return
  }

  const text = await response.text()
  const payload = text ? (JSON.parse(text) as unknown) : undefined
  throw new ApiError(response.status, parseErrorDetail(payload))
}

function filenameFromDisposition(disposition: string | null): string {
  const fallback = 'learning-coach-db-backup.dump'
  if (!disposition) {
    return fallback
  }

  const match = /filename="([^"]+)"/.exec(disposition)
  return match?.[1] ?? fallback
}

export async function exportDatabaseBackup(): Promise<void> {
  const response = await fetch('/api/database-backups/export', {
    method: 'GET',
    credentials: 'include',
  })
  await raiseForError(response)

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filenameFromDisposition(
    response.headers.get('Content-Disposition'),
  )
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function restoreDatabaseBackup(
  file: File,
): Promise<RestoreDatabaseBackupResult> {
  const response = await fetch('/api/database-backups/restore', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/octet-stream',
    },
    body: file,
  })
  await raiseForError(response)
  return (await response.json()) as RestoreDatabaseBackupResult
}
