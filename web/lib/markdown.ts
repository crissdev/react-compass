export type MarkdownPart =
  | { type: 'markdown'; content: string }
  | { type: 'sandpack'; files: Record<string, string> };

export type MarkdownSection = {
  type: 'content' | 'citations';
  content: string;
};

const SANDPACK_PATTERN = /<Sandpack(?:\s[^>]*)?>([\s\S]*?)<\/Sandpack>/gi;
const FENCE_PATTERN = /```([\w+-]*)([^\n]*)\n([\s\S]*?)```/g;
const MIXED_MARKDOWN_FENCE_PATTERN =
  /^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([\w+-]*)[^\n]*\r?\n([\s\S]*?)^[ \t]{0,3}\1[ \t]*$/gm;
const PROSE_FENCE_PATTERN =
  /^[ \t]{0,3}(`{3,}|~{3,})[ \t]*(?:text|markdown|md)?[ \t]*\r?\n([\s\S]*?)^[ \t]{0,3}\1[ \t]*$/gim;
const UNTERMINATED_PROSE_FENCE_PATTERN =
  /^[ \t]{0,3}(?:`{3,}|~{3,})[ \t]*(?:text|markdown|md)?[ \t]*\r?\n([\s\S]*?)(?=\r?\n<Sandpack(?:\s|>))/gim;
const STRAY_CITATION_FENCE_PATTERN = /^[ \t]*(?:`{3,}|~{3,})[ \t]+(?=\[\d+\](?:\s|$))/gm;
const REACT_NOTE_PATTERN = /<Note>\s*([\s\S]*?)\s*<\/Note>/gi;
const CODE_PATTERN = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g;
const CITATION_PATTERN = /([ \t]*)(?<!\\)\[(\d+)\](?!\s*[:(])/g;
const SOURCE_CITATION_PREFIX = '#docchat-source-';
const MARKDOWN_HEADING_PATTERN = /^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$/gm;
const REACT_DOCS_ANCHOR_PATTERN = /[ \t]*\{\/\*[a-z0-9_-]+\*\/\}/gi;

export function cleanSourceExcerpt(content: string): string {
  return content.replace(REACT_DOCS_ANCHOR_PATTERN, '');
}

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

      return segment.replace(CITATION_PATTERN, (match, _leadingSpace: string, value: string) => {
        const citation = Number(value);
        return availableCitations.has(citation)
          ? `[${citation}](${sourceCitationHref(citation)})`
          : match;
      });
    })
    .join('');
}

export function splitCitationSections(content: string): MarkdownSection[] {
  MARKDOWN_HEADING_PATTERN.lastIndex = 0;
  const headings = [...content.matchAll(MARKDOWN_HEADING_PATTERN)];
  const citationHeadingIndex = headings.findIndex(
    (heading) => heading[2].trim().toLowerCase() === 'citations',
  );
  if (citationHeadingIndex < 0) return [{ type: 'content', content }];

  const citationHeading = headings[citationHeadingIndex];
  const citationLevel = citationHeading[1].length;
  const citationStart = citationHeading.index;
  const nextSection = headings
    .slice(citationHeadingIndex + 1)
    .find((heading) => heading[1].length <= citationLevel);
  const citationEnd = nextSection?.index ?? content.length;
  const sections: MarkdownSection[] = [];

  if (citationStart > 0) {
    sections.push({ type: 'content', content: content.slice(0, citationStart) });
  }
  sections.push({ type: 'citations', content: content.slice(citationStart, citationEnd) });
  if (citationEnd < content.length) {
    sections.push({ type: 'content', content: content.slice(citationEnd) });
  }

  return sections;
}

export function unwrapProseFences(content: string): string {
  const recoverMixedMarkdownFence = (
    fence: string,
    _outerMarker: string,
    language: string,
    body: string,
  ): string => {
    const heading = body.match(/^#{1,6}\s+\S/m);
    const nestedFences = [
      ...body.matchAll(/^[ \t]{0,3}(`{3}|~{3})(?:[\w+-]+)?[^\n]*$/gm),
    ];
    if (heading?.index === undefined || nestedFences.length === 0) return fence;

    let leadingCode = body.slice(0, heading.index).trim();
    const markdown = body.slice(heading.index).trim();
    const citation = leadingCode.match(/(?:^|\n)[ \t]*(\[\d+\])[ \t]*$/)?.[1];
    if (citation) {
      leadingCode = leadingCode.replace(/(?:^|\n)[ \t]*\[\d+\][ \t]*$/, '').trimEnd();
    }

    const nestedMarker = nestedFences[0][1];
    const nestedClosingFence = nestedFences.length % 2 === 1 ? `\n${nestedMarker}` : '';
    const recoveredParts: string[] = [];
    if (leadingCode) {
      recoveredParts.push(`\`\`\`${language || 'text'}\n${leadingCode}\n\`\`\``);
    }
    if (citation) recoveredParts.push(citation);
    recoveredParts.push(`${markdown}${nestedClosingFence}`);

    return `\n${recoveredParts.join('\n\n')}\n`;
  };

  const unwrapMalformedFence = (fence: string, body: string): string => {
    const lines = body
      .trim()
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const isProseList = lines.length > 1 && lines.every((line) => /^[-*]\s+\S/.test(line));
    return isProseList ? `\n${body.trim()}\n` : fence;
  };

  return content
    .replace(MIXED_MARKDOWN_FENCE_PATTERN, recoverMixedMarkdownFence)
    .replace(PROSE_FENCE_PATTERN, (fence, _marker: string, body: string) =>
      unwrapMalformedFence(fence, body),
    )
    .replace(UNTERMINATED_PROSE_FENCE_PATTERN, (fence, body: string) =>
      unwrapMalformedFence(fence, body),
    )
    .replace(STRAY_CITATION_FENCE_PATTERN, '')
    .replace(REACT_NOTE_PATTERN, (_note, body: string) =>
      body
        .trim()
        .split(/\r?\n/)
        .map((line) => `> ${line}`)
        .join('\n'),
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
