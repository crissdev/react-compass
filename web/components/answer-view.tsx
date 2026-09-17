'use client';

import { ExternalLink, FileText } from 'lucide-react';
import { Fragment } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import {
  citationFromHref,
  cleanSourceExcerpt,
  linkSourceCitations,
  splitCitationSections,
  splitMarkdown,
  unwrapProseFences,
} from '@/lib/markdown';
import type { Answer } from '@/lib/types';
import { SandpackExample } from './sandpack-example';

export function AnswerView({ answer }: { answer: Answer }) {
  const hasSources = answer.sources.length > 0;
  const sourcesByCitation = new Map(answer.sources.map((source) => [source.citation, source]));
  const message = linkSourceCitations(
    unwrapProseFences(answer.message),
    answer.sources.filter((source) => source.source_url).map((source) => source.citation),
  );
  const sections = splitCitationSections(message);

  return (
    <article
      className={hasSources ? 'answer-layout' : 'answer-layout answer-layout-standalone'}
      aria-live="polite"
    >
      <section className="answer-card">
        <div className="answer-heading">
          <span className="answer-mark">R</span>
          <div>
            <p className="eyebrow">React DocChat</p>
            <h2>{hasSources ? 'Answer from the docs' : 'React questions only'}</h2>
          </div>
        </div>
        <div className="markdown-body">
          {sections.map((section, sectionIndex) => {
            const content = splitMarkdown(section.content).map((part, partIndex) =>
              part.type === 'sandpack' ? (
                <SandpackExample
                  key={`sandpack-${sectionIndex}-${partIndex}`}
                  files={part.files}
                />
              ) : (
                <ReactMarkdown
                  key={`markdown-${sectionIndex}-${partIndex}`}
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
                            data-debug-source-citation={source.citation}
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
            );

            return section.type === 'citations' ? (
              <div className="citations-section" key={`section-${sectionIndex}`}>
                {content}
              </div>
            ) : (
              <Fragment key={`section-${sectionIndex}`}>{content}</Fragment>
            );
          })}
        </div>
      </section>

      {hasSources && (
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
                <div className="source-copy">
                  <span className="source-type">{source.source_type}</span>
                  <strong className="source-title">{source.title}</strong>
                  {source.section && <span className="source-section">{source.section}</span>}
                  <div className="source-excerpt">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ children }) => <>{children}</>,
                      }}
                    >
                      {cleanSourceExcerpt(source.excerpt)}
                    </ReactMarkdown>
                  </div>
                </div>
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            ))}
          </div>
        </aside>
      )}
    </article>
  );
}
