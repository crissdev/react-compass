import type { Metadata } from 'next';
import 'highlight.js/styles/github.css';
import './globals.css';

const themeScript = `
  (function () {
    try {
      var theme = localStorage.getItem('react-compass-theme');
      var isDarkTheme =
        theme === 'dark' ||
        (!theme && window.matchMedia('(prefers-color-scheme: dark)').matches);

      document.documentElement.setAttribute(
        'data-theme',
        isDarkTheme ? 'dark' : 'light',
      );
    } catch (error) {}
  })();
`;

export const metadata: Metadata = {
  title: 'React Compass',
  description:
    'Explore React documentation with grounded answers and runnable examples.',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <head>
        <title>React Compass</title>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
