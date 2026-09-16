'use client';

import { ExternalLink, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { citationFromHref, linkSourceCitations, splitMarkdown } from '@/lib/markdown';
import type { Answer } from '@/lib/types';
import { SandpackExample } from './sandpack-example';

export function AnswerView({ answer }: { answer: Answer }) {
  const sourcesByCitation = new Map(answer.sources.map((source) => [source.citation, source]));
  const message = linkSourceCitations(
    answer.message,
    answer.sources.filter((source) => source.source_url).map((source) => source.citation),
  );
  const parts = splitMarkdown(message);

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
                  a: ({ children, href, ...props }) => {
                    const citation = citationFromHref(href);
                    const source = citation ? sourcesByCitation.get(citation) : undefined;

                    if (source) {
                      return (
                        <a
                          {...props}
                          className="source-citation"
                          href={source.source_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Open source ${source.citation}: ${source.title} in a new tab`}
                          title={`${source.title}${source.section ? ` — ${source.section}` : ''}`}
                        >
                          <FileText size={11} aria-hidden="true" />
                          <span className="source-citation-label">{source.title}</span>
                          <span className="source-citation-number" aria-hidden="true">
                            {source.citation}
                          </span>
                        </a>
                      );
                    }

                    return (
                      <a {...props} href={href} target="_blank" rel="noreferrer">
                        {children}
                      </a>
                    );
                  },
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
