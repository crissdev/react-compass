'use client';

import { FormEvent, MouseEvent, useRef, useState } from 'react';
import { ArrowUp, BookOpen, CircleStop, Github, Sparkles } from 'lucide-react';
import { readAnswerStream } from '@/lib/answer-stream';
import { addSearchHistoryItem, removeSearchHistoryItem } from '@/lib/search-history';
import { saveSearchHistory, useSearchHistory } from '@/lib/search-history-store';
import type { Answer } from '@/lib/types';
import { AnswerView } from './answer-view';
import { SearchHistory } from './search-history';
import { ThemeToggle } from './theme-toggle';

const suggestions = [
  {
    label: 'State updates',
    question: 'How does useState work, and when should I use an updater function?',
  },
  {
    label: 'Effects',
    question: 'When do I not need an Effect in React?',
  },
  {
    label: 'Performance',
    question: 'How does useMemo work and when is it useful?',
  },
  {
    label: 'React 19',
    question: 'What does the Activity component do?',
  },
];

export function DocChat() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [removingQuestion, setRemovingQuestion] = useState<string | null>(null);
  const searchHistory = useSearchHistory();
  const controllerRef = useRef<AbortController | null>(null);

  async function ask(nextQuestion = question) {
    const value = nextQuestion.trim();
    if (value.length < 2 || isLoading) return;

    setQuestion(value);
    setAnswer(null);
    setError('');
    setStatus('Connecting to the documentation index');
    setIsLoading(true);
    saveSearchHistory(addSearchHistoryItem(searchHistory, value));
    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: value }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { message?: string } | null;
        throw new Error(payload?.message || 'The search could not be completed.');
      }

      await readAnswerStream(
        response,
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === 'status') setStatus(event.message);
          if (event.type === 'result') setAnswer(event.data);
          if (event.type === 'error') setError(event.message);
        },
        controller.signal,
      );
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') {
        setStatus('Search cancelled');
      } else {
        setError(caught instanceof Error ? caught.message : 'Something went wrong.');
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setIsLoading(false);
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask();
  }

  function cancel(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    controllerRef.current?.abort();
    controllerRef.current = null;
    setStatus('Search cancelled');
    setIsLoading(false);
  }

  async function removeHistory(questionToRemove: string) {
    setRemovingQuestion(questionToRemove);
    setError('');

    try {
      const response = await fetch('/api/ask', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: questionToRemove }),
      });
      if (!response.ok) throw new Error('Could not remove that saved search.');
      saveSearchHistory(removeSearchHistoryItem(searchHistory, questionToRemove));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not remove that saved search.');
    } finally {
      setRemovingQuestion(null);
    }
  }

  return (
    <main className={answer ? 'app-shell has-answer' : 'app-shell'}>
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <header className="topbar">
        {/* A native anchor intentionally reloads the app and clears the current client state. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a className="brand" href="/" aria-label="Reload DocChat and start a new search">
          <span className="brand-icon">R</span>
          <span>DocChat</span>
        </a>
        <nav aria-label="Source links">
          <a
            href="https://react.dev"
            target="_blank"
            rel="noreferrer"
            aria-label="Open React documentation"
          >
            <BookOpen size={16} /> <span>React docs</span>
          </a>
          <a
            href="https://github.com/facebook/react"
            target="_blank"
            rel="noreferrer"
            aria-label="Open React GitHub repository"
          >
            <Github size={16} /> <span>GitHub</span>
          </a>
          <ThemeToggle />
        </nav>
      </header>

      <section className="hero" id="top">
        <div className="hero-badge">
          <Sparkles size={14} /> Grounded in the official React docs
        </div>
        <h1>
          Ask React.
          <span> Understand the why.</span>
        </h1>
        <p className="hero-copy">
          Search the React reference and learning guides. Get a focused answer with source excerpts
          and runnable examples.
        </p>

        <form className="search-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="question">
            Ask a question about React
          </label>
          <input
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="How does useEffect work?"
            autoComplete="off"
            maxLength={1000}
            readOnly={isLoading}
          />
          {isLoading ? (
            <button className="cancel-button" type="button" onClick={cancel}>
              <CircleStop size={18} />
              <span>Cancel</span>
            </button>
          ) : (
            <button className="ask-button" type="submit" disabled={question.trim().length < 2}>
              <span>Ask</span>
              <ArrowUp size={18} />
            </button>
          )}
        </form>

        {isLoading && (
          <div className="progress" role="status">
            <span className="progress-track">
              <span className="progress-bar" />
            </span>
            <span>{status}</span>
          </div>
        )}

        {error && (
          <div className="error-message" role="alert">
            {error}
          </div>
        )}

        {!answer && !isLoading && (
          <>
            <div className="suggestions">
              <p>Try asking</p>
              <div className="suggestion-grid">
                {suggestions.map((suggestion) => (
                  <button
                    type="button"
                    key={suggestion.label}
                    onClick={() => void ask(suggestion.question)}
                  >
                    <span>{suggestion.label}</span>
                    {suggestion.question}
                  </button>
                ))}
              </div>
            </div>

            <SearchHistory
              items={searchHistory}
              removingQuestion={removingQuestion}
              onSelect={(historyQuestion) => void ask(historyQuestion)}
              onRemove={(historyQuestion) => void removeHistory(historyQuestion)}
            />
          </>
        )}
      </section>

      {answer && <AnswerView answer={answer} />}

      <footer>
        Answers are generated from retrieved documentation. Check the cited source for details.
      </footer>
    </main>
  );
}
