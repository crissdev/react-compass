'use client';

import dynamic from 'next/dynamic';

const Sandpack = dynamic(
  () => import('@codesandbox/sandpack-react').then((module) => module.Sandpack),
  {
    ssr: false,
    loading: () => <div className="sandpack-loading">Preparing interactive example…</div>,
  },
);

export function SandpackExample({ files }: { files: Record<string, string> }) {
  return (
    <div className="sandpack-shell">
      <div className="example-label">
        <span className="live-dot" /> Interactive example
      </div>
      <Sandpack
        template="react"
        files={files}
        theme="dark"
        options={{
          showNavigator: true,
          showTabs: true,
          editorHeight: 360,
          wrapContent: true,
        }}
      />
    </div>
  );
}
