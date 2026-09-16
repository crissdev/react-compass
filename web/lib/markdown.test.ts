import { describe, expect, it } from 'vitest';
import {
  citationFromHref,
  linkSourceCitations,
  parseSandpackFiles,
  sourceCitationHref,
  splitMarkdown,
} from './markdown';

describe('React docs Sandpack parsing', () => {
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
      'Read [1](#docchat-source-1) and [4]. Keep `[1]` and ```js\nconst ref = "[1]";\n``` unchanged.',
    );
  });

  it('recognizes only valid source citation links', () => {
    expect(sourceCitationHref(3)).toBe('#docchat-source-3');
    expect(citationFromHref('#docchat-source-3')).toBe(3);
    expect(citationFromHref('#docchat-source-nope')).toBeNull();
    expect(citationFromHref('https://react.dev')).toBeNull();
  });
});
