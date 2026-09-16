import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AnswerView } from './answer-view';

describe('AnswerView citations', () => {
  it('wraps an explicit Citations section while retaining citations elsewhere for debugging', () => {
    const markup = renderToStaticMarkup(
      <AnswerView
        answer={{
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
});
