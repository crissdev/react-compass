export type MarkdownPart =
  | { type: 'markdown'; content: string }
  | { type: 'sandpack'; files: Record<string, string> };

const SANDPACK_PATTERN = /<Sandpack(?:\s[^>]*)?>([\s\S]*?)<\/Sandpack>/gi;
const FENCE_PATTERN = /```([\w+-]*)([^\n]*)\n([\s\S]*?)```/g;
const PROSE_FENCE_PATTERN =
  /^[ \t]{0,3}(`{3,}|~{3,})[ \t]*(?:text|markdown|md)?[ \t]*\r?\n([\s\S]*?)^[ \t]{0,3}\1[ \t]*$/gim;
const UNTERMINATED_PROSE_FENCE_PATTERN =
  /^[ \t]{0,3}(?:`{3,}|~{3,})[ \t]*(?:text|markdown|md)?[ \t]*\r?\n([\s\S]*?)(?=\r?\n<Sandpack(?:\s|>))/gim;
const CODE_PATTERN = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g;
const CITATION_PATTERN = /(?<!\\)\[(\d+)\](?!\s*[:(])/g;
const SOURCE_CITATION_PREFIX = '#docchat-source-';

export function sourceCitationHref(citation: number): string {
  return `${SOURCE_CITATION_PREFIX}${citation}`;
}

export function citationFromHref(href: string | undefined): number | null {
  if (!href?.startsWith(SOURCE_CITATION_PREFIX)) return null;

  const value = Number(href.slice(SOURCE_CITATION_PREFIX.length));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function linkSourceCitations(content: string, citations: readonly number[]): string {
  const availableCitations = new Set(citations);

  return content
    .split(CODE_PATTERN)
    .map((segment, index) => {
      if (index % 2 === 1) return segment;

      return segment.replace(CITATION_PATTERN, (match, value: string) => {
        const citation = Number(value);
        return availableCitations.has(citation)
          ? `[${citation}](${sourceCitationHref(citation)})`
          : match;
      });
    })
    .join('');
}

export function unwrapProseFences(content: string): string {
  const unwrapIfProseList = (fence: string, body: string): string => {
    const lines = body
      .trim()
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const isProseList = lines.length > 1 && lines.every((line) => /^[-*]\s+\S/.test(line));

    return isProseList ? `\n${body.trim()}\n` : fence;
  };

  return content
    .replace(PROSE_FENCE_PATTERN, (fence, _marker: string, body: string) =>
      unwrapIfProseList(fence, body),
    )
    .replace(UNTERMINATED_PROSE_FENCE_PATTERN, (fence, body: string) =>
      unwrapIfProseList(fence, body),
    );
}

function extensionFor(language: string): string {
  if (language === 'tsx' || language === 'typescript') return 'tsx';
  if (language === 'ts') return 'ts';
  if (language === 'jsx' || language === 'javascript') return 'js';
  return language || 'txt';
}

function normalizeFilename(meta: string, language: string, index: number): string {
  const explicit = meta.trim().match(/[\w./-]+\.[a-z0-9]+/i)?.[0];
  if (explicit) {
    const withoutPrefix = explicit.replace(/^\.?\/?src\//, '');
    return `/${withoutPrefix}`;
  }

  if (['js', 'jsx', 'javascript', 'ts', 'tsx', 'typescript'].includes(language)) {
    return index === 0 ? '/App.js' : `/Example${index + 1}.${extensionFor(language)}`;
  }
  if (language === 'css') return '/styles.css';
  return `/example-${index + 1}.${extensionFor(language)}`;
}

export function parseSandpackFiles(content: string): Record<string, string> {
  const files: Record<string, string> = {};
  let match: RegExpExecArray | null;
  let index = 0;
  FENCE_PATTERN.lastIndex = 0;

  while ((match = FENCE_PATTERN.exec(content))) {
    const language = match[1].toLowerCase();
    const filename = normalizeFilename(match[2], language, index);
    files[filename] = match[3].trimEnd();
    index += 1;
  }

  if (files['/styles.css'] && files['/App.js'] && !files['/App.js'].includes("'./styles.css'")) {
    files['/App.js'] = `import './styles.css';\n${files['/App.js']}`;
  }

  return files;
}

export function splitMarkdown(content: string): MarkdownPart[] {
  const parts: MarkdownPart[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  SANDPACK_PATTERN.lastIndex = 0;

  while ((match = SANDPACK_PATTERN.exec(content))) {
    if (match.index > cursor) {
      parts.push({ type: 'markdown', content: content.slice(cursor, match.index) });
    }
    const files = parseSandpackFiles(match[1]);
    if (Object.keys(files).length) {
      parts.push({ type: 'sandpack', files });
    } else {
      parts.push({ type: 'markdown', content: match[0] });
    }
    cursor = match.index + match[0].length;
  }

  if (cursor < content.length) {
    parts.push({ type: 'markdown', content: content.slice(cursor) });
  }

  return parts.length ? parts : [{ type: 'markdown', content }];
}
