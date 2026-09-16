import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AnswerView } from './answer-view';

describe('AnswerView citations', () => {
  it('wraps an explicit Citations section while retaining citations elsewhere for debugging', () => {
    const markup = renderToStaticMarkup(
      <AnswerView
        answer={{
          kind: 'react_answer',
          message: '## Overview\nReact remembers state [1].\n\n## Citations\n- State guide: [1]',
          sources: [
            {
              id: 'state-guide',
              citation: 1,
              title: 'State: A Component’s Memory',
              section: 'React remembers state',
              source_type: 'learn',
              source_url: 'https://react.dev/learn/state-a-components-memory',
              excerpt: 'State lets a component remember information between renders.',
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
          message: 'I can only answer questions about React and its official documentation.',
          sources: [],
        }}
      />,
    );

    expect(markup).toContain('answer-layout-standalone');
    expect(markup).toContain('React questions only');
    expect(markup).not.toContain('Documentation sources');
  });
});
