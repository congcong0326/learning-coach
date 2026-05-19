import { requestJson } from './client'

export type ProblemTag = {
  slug: string
  name: string
  translated_name: string
}

export type ProblemCategorySummary = {
  slug: string
  name: string
  description: string
}

export type ProblemListItem = {
  id: number
  frontend_id: string
  slug: string
  title: string
  translated_title: string
  difficulty: 'Easy' | 'Medium' | 'Hard'
  tags: ProblemTag[]
  categories: ProblemCategorySummary[]
}

export type ProblemListResponse = {
  items: ProblemListItem[]
  total: number
  page: number
  page_size: number
}

export type ProblemDetail = ProblemListItem & {
  statement_md: string
  leetcode_url: string
  sample_test_case: string
  python3_snippet: string
}

export function getProblems(): Promise<ProblemListResponse> {
  return requestJson<ProblemListResponse>('/api/problems')
}

export function getProblem(slug: string): Promise<ProblemDetail> {
  return requestJson<ProblemDetail>(`/api/problems/${encodeURIComponent(slug)}`)
}
