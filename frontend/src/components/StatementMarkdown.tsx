import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

function selectChineseStatementMarkdown(markdown: string): string {
  const lines = markdown.split(/\r?\n/)
  const translationHeadingIndex = lines.findIndex((line) =>
    /^##\s*翻译\s*$/.test(line.trim()),
  )

  if (translationHeadingIndex === -1) {
    return markdown.trim()
  }

  // 题库源可能包含中英完整题面；页面优先展示中文翻译段，避免用户先读到英文原文。
  const translatedMarkdown = lines.slice(translationHeadingIndex + 1).join('\n').trim()
  return translatedMarkdown || markdown.trim()
}

export function StatementMarkdown({ markdown }: { markdown: string }) {
  return (
    <div className="markdown-statement">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeSanitize]}
        components={{
          a: ({ href, title, children }) => (
            <a href={href} title={title} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          img: ({ src, alt, title }) =>
            src ? (
              <img
                src={src}
                alt={alt ?? ''}
                title={title}
                loading="lazy"
                decoding="async"
                referrerPolicy="no-referrer"
              />
            ) : null,
        }}
      >
        {selectChineseStatementMarkdown(markdown)}
      </ReactMarkdown>
    </div>
  )
}
