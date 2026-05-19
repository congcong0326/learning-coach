import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const healthResponse = {
  status: 'ok',
  service: 'learning-coach-backend',
}

describe('App shell', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        return new Response(JSON.stringify(healthResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.pushState({}, '', '/')
  })

  it('renders product navigation and backend health status', async () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'Agentic Coding Learning Coach' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '题库' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '工作台' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '复盘' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Trace' })).toBeInTheDocument()
    expect(await screen.findByText('API 正常')).toBeInTheDocument()
  })

  it('redirects the root route to the problem library', async () => {
    window.history.pushState({}, '', '/')

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: '题库列表' }),
    ).toBeInTheDocument()
  })

  it('renders the workspace route', async () => {
    window.history.pushState({}, '', '/workspace')

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: '做题工作台' }),
    ).toBeInTheDocument()
  })
})
