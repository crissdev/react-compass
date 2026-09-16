import { describe, expect, it } from 'vitest';
import { parseSandpackFiles, splitMarkdown } from './markdown';

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
});
