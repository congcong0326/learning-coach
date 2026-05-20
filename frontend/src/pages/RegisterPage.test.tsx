import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RegisterPage } from './RegisterPage'

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RegisterPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('submits local user registration through the auth API', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          user: {
            id: 1,
            username: 'alice',
            email: 'alice@example.com',
            display_name: 'alice',
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.change(screen.getByLabelText('用户名'), {
      target: { value: 'alice' },
    })
    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'alice@example.com' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'password123' },
    })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/register',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          username: 'alice',
          email: 'alice@example.com',
          password: 'password123',
        }),
      }),
    ))
  })
})
