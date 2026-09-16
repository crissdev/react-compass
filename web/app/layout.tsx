import type { Metadata } from 'next';
import 'highlight.js/styles/github.css';
import './globals.css';

const themeScript = `(function(){try{var t=localStorage.getItem('docchat-theme');var d=t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.setAttribute('data-theme',d?'dark':'light')}catch(e){}})()`;

export const metadata: Metadata = {
  title: 'React DocChat',
  description: 'Explore React documentation with grounded answers and runnable examples.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
