import { describe, expect, it } from 'vitest';
import {
  citationFromHref,
  cleanSourceExcerpt,
  linkSourceCitations,
  parseSandpackFiles,
  sourceCitationHref,
  splitCitationSections,
  splitMarkdown,
  unwrapProseFences,
} from './markdown';

describe('React docs Sandpack parsing', () => {
  it('removes React docs heading anchors from source excerpts', () => {
    expect(
      cleanSourceExcerpt(
        '## Where you can cause side effects {/*where-you-_can_-cause-side-effects*/}\n\n**Prefer events.**',
      ),
    ).toBe('## Where you can cause side effects\n\n**Prefer events.**');
  });

  it('maps React docs filenames and adds the stylesheet import', () => {
    const files = parseSandpackFiles(`
\`\`\`js src/App.js
export default function App() { return <h1>Hello</h1>; }
\`\`\`
\`\`\`css
h1 { color: teal; }
\`\`\`
`);

    expect(files['/App.js']).toContain("import './styles.css';");
    expect(files['/styles.css']).toContain('color: teal');
  });

  it('keeps prose around an interactive example', () => {
    const parts = splitMarkdown('Before\n<Sandpack>\n```js\nexport default () => null\n```\n</Sandpack>\nAfter');
    expect(parts.map((part) => part.type)).toEqual(['markdown', 'sandpack', 'markdown']);
  });

  it('links known source citations without changing code examples or unknown citations', () => {
    const content = 'Read [1] and [4]. Keep `[1]` and ```js\nconst ref = "[1]";\n``` unchanged.';

    expect(linkSourceCitations(content, [1])).toBe(
      'Read[1](#docchat-source-1) and [4]. Keep `[1]` and ```js\nconst ref = "[1]";\n``` unchanged.',
    );
  });

  it('recognizes only valid source citation links', () => {
    expect(sourceCitationHref(3)).toBe('#docchat-source-3');
    expect(citationFromHref('#docchat-source-3')).toBe(3);
    expect(citationFromHref('#docchat-source-nope')).toBeNull();
    expect(citationFromHref('https://react.dev')).toBeNull();
  });

  it('isolates a citations section until the next heading at the same level', () => {
    const content =
      '## Overview\nClaim [1].\n\n## Citations\n- Source [1]\n\n## Follow-up\nMore detail [1].';

    expect(splitCitationSections(content)).toEqual([
      { type: 'content', content: '## Overview\nClaim [1].\n\n' },
      { type: 'citations', content: '## Citations\n- Source [1]\n\n' },
      { type: 'content', content: '## Follow-up\nMore detail [1].' },
    ]);
  });

  it('turns a prose-only fenced list back into Markdown', () => {
    const content = 'Before\n````\n- First explanation\n- Second explanation\n````\nAfter';

    expect(unwrapProseFences(content)).toBe(
      'Before\n\n- First explanation\n- Second explanation\n\nAfter',
    );
  });

  it('recovers a prose fence left open immediately before a Sandpack', () => {
    const content =
      '~~~\n- First explanation\n- Second explanation\n\n<Sandpack>\n```js\nexport default () => null\n```\n</Sandpack>';

    expect(unwrapProseFences(content)).toBe(
      '\n- First explanation\n- Second explanation\n\n<Sandpack>\n```js\nexport default () => null\n```\n</Sandpack>',
    );
  });

  it('recovers Markdown and a nested code block from an accidental outer fence', () => {
    const content =
      '````\n## Fetching data\nUse an Effect carefully.\n\n```js\nuseEffect(loadData, []);\n````\n\n``` [2]';

    expect(unwrapProseFences(content)).toBe(
      '\n## Fetching data\nUse an Effect carefully.\n\n```js\nuseEffect(loadData, []);\n```\n\n\n[2]',
    );
  });

  it('preserves leading code when a malformed fence also contains a Markdown section', () => {
    const content =
      '````js\nconst albums = await loadAlbums();\n\n[4]\n\n## Custom hooks\nExample:\n```js\nuseOnlineStatus();\n````';

    expect(unwrapProseFences(content)).toBe(
      '\n```js\nconst albums = await loadAlbums();\n```\n\n[4]\n\n## Custom hooks\nExample:\n```js\nuseOnlineStatus();\n```\n',
    );
  });

  it('turns React documentation Note markup into a Markdown callout', () => {
    expect(unwrapProseFences('<Note>Prefer a data library.</Note>')).toBe(
      '> Prefer a data library.',
    );
  });

  it('preserves real code and single-line text fences', () => {
    expect(unwrapProseFences('```js\nconst value = 1;\n```')).toBe(
      '```js\nconst value = 1;\n```',
    );
    expect(unwrapProseFences('```text\n- a command argument\n```')).toBe(
      '```text\n- a command argument\n```',
    );
    expect(unwrapProseFences('```diff\n- removed first line\n- removed second line\n```')).toBe(
      '```diff\n- removed first line\n- removed second line\n```',
    );
  });
});
