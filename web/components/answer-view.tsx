'use client';

import { ExternalLink, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { splitMarkdown } from '@/lib/markdown';
import type { Answer } from '@/lib/types';
import { SandpackExample } from './sandpack-example';

export function AnswerView({ answer }: { answer: Answer }) {
  const parts = splitMarkdown(answer.message);

  return (
    <article className="answer-layout" aria-live="polite">
      <section className="answer-card">
        <div className="answer-heading">
          <span className="answer-mark">R</span>
          <div>
            <p className="eyebrow">React DocChat</p>
            <h2>Answer from the docs</h2>
          </div>
        </div>
        <div className="markdown-body">
          {parts.map((part, index) =>
            part.type === 'sandpack' ? (
              <SandpackExample key={`sandpack-${index}`} files={part.files} />
            ) : (
              <ReactMarkdown
                key={`markdown-${index}`}
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={{
                  a: ({ children, ...props }) => (
                    <a {...props} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  ),
                }}
              >
                {part.content}
              </ReactMarkdown>
            ),
          )}
        </div>
      </section>

      <aside className="sources-panel" aria-label="Documentation sources">
        <div className="sources-heading">
          <FileText size={17} aria-hidden="true" />
          <h2>Sources</h2>
          <span>{answer.sources.length}</span>
        </div>
        <div className="source-list">
          {answer.sources.map((source) => (
            <a
              className="source-card"
              href={source.source_url}
              target="_blank"
              rel="noreferrer"
              key={`${source.id}-${source.source_url}`}
            >
              <span className="source-number">{source.citation}</span>
              <span className="source-copy">
                <span className="source-type">{source.source_type}</span>
                <strong>{source.title}</strong>
                {source.section && <span className="source-section">{source.section}</span>}
                <span className="source-excerpt">{source.excerpt}</span>
              </span>
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          ))}
        </div>
      </aside>
    </article>
  );
}
