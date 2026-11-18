import ReactMarkdown, { type Components } from 'react-markdown'
import { Link } from 'react-router'
import remarkGfm from 'remark-gfm'

import { isRecordLink } from './useAssistant'

// Assistant answers are Markdown from the model, built partly from CRM text (untrusted).
// Rendered without raw HTML (`skipHtml`, no rehype-raw; architecture 7 "Output"), images
// are dropped, and only in-app record links become links: anything else stays text.
const components: Components = {
  a: ({ href, children }) =>
    href && isRecordLink(href) ? (
      <Link to={href} className="text-primary underline underline-offset-2">
        {children}
      </Link>
    ) : (
      <span>{children}</span>
    ),
  img: () => null,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children, style }) => (
    <th className="border-b px-2 py-1 text-left font-medium" style={style}>
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td className="border-b px-2 py-1" style={style}>
      {children}
    </td>
  ),
  ul: ({ children }) => <ul className="my-1 list-disc pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal pl-5">{children}</ol>,
  p: ({ children }) => <p className="my-1">{children}</p>,
  h1: ({ children }) => <p className="my-1 font-semibold">{children}</p>,
  h2: ({ children }) => <p className="my-1 font-semibold">{children}</p>,
  h3: ({ children }) => <p className="my-1 font-semibold">{children}</p>,
  pre: ({ children }) => (
    <pre className="my-1 overflow-x-auto rounded bg-muted p-2 text-xs">{children}</pre>
  ),
  code: ({ children }) => <code className="rounded bg-muted px-1 text-xs">{children}</code>,
}

export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
      {text}
    </ReactMarkdown>
  )
}
