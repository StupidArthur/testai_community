/**
 * 工具文档 Markdown 展示（内部纵向滚动）。
 */
import ReactMarkdown from 'react-markdown'

export interface ToolMarkdownPanelProps {
  markdown: string
}

export default function ToolMarkdownPanel({ markdown }: ToolMarkdownPanelProps) {
  return (
    <div
      className="changelog-content"
      style={{
        flex: 1,
        minHeight: 0,
        overflowY: 'auto',
        padding: '16px 20px',
        border: '1px solid var(--color-border)',
        borderRadius: 8,
        background: 'var(--color-bg)',
      }}
    >
      <ReactMarkdown>{markdown || '_暂无文档_'}</ReactMarkdown>
    </div>
  )
}
