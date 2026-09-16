'use client';

import type { SandpackTheme } from '@codesandbox/sandpack-react';
import dynamic from 'next/dynamic';

const reactDocsTheme: SandpackTheme = {
  colors: {
    accent: '#087ea4',
    base: '#23272f',
    clickable: '#5f6b76',
    disabled: '#a9b1b8',
    error: '#811e18',
    errorSurface: '#ffcdca',
    hover: '#f6f7f9',
    surface1: '#ffffff',
    surface2: '#e4e7eb',
    surface3: '#f6f7f9',
  },
  syntax: {
    plain: '#24292e',
    comment: '#6a737d',
    keyword: '#d73a49',
    tag: '#22863a',
    punctuation: '#24292e',
    definition: '#6f42c1',
    property: '#005cc5',
    static: '#032f62',
    string: '#032f62',
  },
  font: {
    body: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    mono: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
    size: '13.6px',
    lineHeight: '24px',
  },
};

const Sandpack = dynamic(
  () => import('@codesandbox/sandpack-react').then((module) => module.Sandpack),
  {
    ssr: false,
    loading: () => <div className="sandpack-loading">Preparing interactive example…</div>,
  },
);

export function SandpackExample({ files }: { files: Record<string, string> }) {
  return (
    <div className="sandpack-shell" aria-label="Interactive React example">
      <Sandpack
        template="react"
        files={files}
        theme={reactDocsTheme}
        options={{
          showNavigator: true,
          showTabs: true,
          showLineNumbers: true,
          editorHeight: 360,
          wrapContent: true,
        }}
      />
    </div>
  );
}
