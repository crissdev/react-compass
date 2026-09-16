'use client';

import { FormEvent, MouseEvent, useRef, useState } from 'react';
import { ArrowUp, BookOpen, CircleStop, Github, Sparkles } from 'lucide-react';
import { readAnswerStream } from '@/lib/answer-stream';
import type { Answer } from '@/lib/types';
import { AnswerView } from './answer-view';

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
  const controllerRef = useRef<AbortController | null>(null);

  async function ask(nextQuestion = question) {
    const value = nextQuestion.trim();
    if (value.length < 2 || isLoading) return;

    setQuestion(value);
    setAnswer(null);
    setError('');
    setStatus('Connecting to the documentation index');
    setIsLoading(true);
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

  return (
    <main className={answer ? 'app-shell has-answer' : 'app-shell'}>
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <header className="topbar">
        <a className="brand" href="#top" aria-label="React DocChat home">
          <span className="brand-icon">R</span>
          <span>DocChat</span>
        </a>
        <nav aria-label="Source links">
          <a href="https://react.dev" target="_blank" rel="noreferrer">
            <BookOpen size={16} /> React docs
          </a>
          <a href="https://github.com/facebook/react" target="_blank" rel="noreferrer">
            <Github size={16} /> GitHub
          </a>
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
        )}
      </section>

      {answer && <AnswerView answer={answer} />}

      <footer>
        Answers are generated from retrieved documentation. Check the cited source for details.
      </footer>
    </main>
  );
}
