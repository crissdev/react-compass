import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AnswerView } from './answer-view';

describe('AnswerView citations', () => {
  it('wraps an explicit Citations section while retaining citations elsewhere for debugging', () => {
    const markup = renderToStaticMarkup(
      <AnswerView
        answer={{
          kind: 'react_answer',
          message:
            '## Overview\nReact remembers state [1].\n\n## Citations\n- State guide: [1]',
          sources: [
            {
              id: 'state-guide',
              citation: 1,
              title: 'State: A Component’s Memory',
              section: 'React remembers state',
              source_type: 'learn',
              source_url: 'https://react.dev/learn/state-a-components-memory',
              excerpt:
                'State lets a component remember information between renders.',
            },
          ],
        }}
      />,
    );

    expect(markup).toContain('class="citations-section"');
    expect(markup.match(/data-debug-source-citation="1"/g)).toHaveLength(2);
    expect(markup).not.toContain(' hidden=""');
  });

  it('renders a scope notice without an empty sources panel', () => {
    const markup = renderToStaticMarkup(
      <AnswerView
        answer={{
          kind: 'scope_notice',
          message:
            'I can only answer questions about React and its official documentation.',
          sources: [],
        }}
      />,
    );

    expect(markup).toContain('answer-layout-standalone');
    expect(markup).toContain('React questions only');
    expect(markup).not.toContain('Documentation sources');
  });

  it('renders suggested questions without retrieved sources for a no-match answer', () => {
    const markup = renderToStaticMarkup(
      <AnswerView
        answer={{
          kind: 'no_match',
          message:
            'The React docs do not directly define stateless components.',
          suggestions: [
            'How should I structure state in React?',
            'When should I avoid redundant state?',
          ],
          sources: [
            {
              id: 'nearby-source',
              citation: 1,
              title: 'Choosing the State Structure',
              section: 'Avoid redundant state',
              source_type: 'learn',
              source_url:
                'https://react.dev/learn/choosing-the-state-structure',
              excerpt: 'Avoid redundant state.',
            },
          ],
        }}
      />,
    );

    expect(markup).toContain('No direct answer found');
    expect(markup).toContain('Try asking instead');
    expect(markup).toContain('How should I structure state in React?');
    expect(markup).toContain('When should I avoid redundant state?');
    expect(markup).not.toContain('Documentation sources');
  });

  it('renders source excerpt Markdown without nesting links inside the source card', () => {
    const markup = renderToStaticMarkup(
      <AnswerView
        answer={{
          kind: 'react_answer',
          message: 'Use an event handler [1].',
          sources: [
            {
              id: 'effects-guide',
              citation: 1,
              title: 'Synchronizing with Effects',
              section: 'You might not need an Effect',
              source_type: 'learn',
              source_url: 'https://react.dev/learn/synchronizing-with-effects',
              excerpt:
                '## Prefer events {/*prefer-events*/}\n\n**Avoid unnecessary Effects.** Read the [guide](/learn/responding-to-events).',
            },
          ],
        }}
      />,
    );

    expect(markup).toContain('<h2>Prefer events</h2>');
    expect(markup).toContain('<strong>Avoid unnecessary Effects.</strong>');
    expect(markup).not.toContain('{/*prefer-events*/}');
    expect(markup).not.toContain('href="/learn/responding-to-events"');
  });
});
