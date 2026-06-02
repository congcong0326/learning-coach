import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BackupRestorePage } from './BackupRestorePage'

const backupApiMocks = vi.hoisted(() => ({
  exportDatabaseBackup: vi.fn(),
  restoreDatabaseBackup: vi.fn(),
}))

vi.mock('../api/databaseBackups', () => ({
  exportDatabaseBackup: backupApiMocks.exportDatabaseBackup,
  restoreDatabaseBackup: backupApiMocks.restoreDatabaseBackup,
}))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <BackupRestorePage />
    </QueryClientProvider>,
  )
}

describe('BackupRestorePage', () => {
  beforeEach(() => {
    backupApiMocks.exportDatabaseBackup.mockReset()
    backupApiMocks.restoreDatabaseBackup.mockReset()
  })

  it('renders export and restore controls', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: '备份恢复' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '导出备份' })).toBeInTheDocument()
    expect(screen.getByLabelText('备份文件')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '恢复数据' })).toBeDisabled()
  })

  it('downloads a database backup file', async () => {
    backupApiMocks.exportDatabaseBackup.mockResolvedValue(undefined)

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: '导出备份' }))

    await waitFor(() =>
      expect(backupApiMocks.exportDatabaseBackup).toHaveBeenCalledTimes(1),
    )
  })

  it('uploads the selected dump after confirmation', async () => {
    backupApiMocks.restoreDatabaseBackup.mockResolvedValue({
      status: 'ok',
      restored_at: '2026-06-02T21:45:00Z',
      file_size_bytes: 16,
    })

    renderPage()

    const file = new File(['PGDMP restore'], 'backup.dump', {
      type: 'application/octet-stream',
    })
    fireEvent.change(screen.getByLabelText('备份文件'), {
      target: { files: [file] },
    })
    fireEvent.click(screen.getByRole('button', { name: '恢复数据' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认恢复' }))

    await waitFor(() =>
      expect(backupApiMocks.restoreDatabaseBackup).toHaveBeenCalled(),
    )
    expect(backupApiMocks.restoreDatabaseBackup.mock.calls[0][0]).toBe(file)
    expect(await screen.findByText('恢复完成')).toBeInTheDocument()
  })
})
