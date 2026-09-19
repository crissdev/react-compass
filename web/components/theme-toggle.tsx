'use client';

import { Moon, Sun } from 'lucide-react';
import { setTheme, useTheme } from '@/lib/theme';

export function ThemeToggle() {
  const theme = useTheme();
  const nextTheme = theme === 'dark' ? 'light' : 'dark';

  return (
    <button
      type="button"
      className="inline-flex size-9 cursor-pointer items-center justify-center rounded-xl border border-[#dfe7ea] bg-white/80 text-[#65727c] transition hover:border-[#afd8e2] hover:bg-white hover:text-[#18232d] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[#58c4dc]/40 dark:border-[#30363d] dark:bg-[#161b22]/90 dark:text-[#a9b4be] dark:hover:border-[#2b8fab] dark:hover:bg-[#1c2128] dark:hover:text-[#f0f6fc]"
      onClick={() => setTheme(nextTheme)}
      aria-label={`Switch to ${nextTheme} theme`}
      title={`Switch to ${nextTheme} theme`}
    >
      {theme === 'dark' ? (
        <Sun size={17} aria-hidden="true" />
      ) : (
        <Moon size={17} aria-hidden="true" />
      )}
    </button>
  );
}
