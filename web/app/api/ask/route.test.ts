import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getCachedAnswer: vi.fn(),
  revalidateTag: vi.fn(),
}));

vi.mock('next/cache', () => ({
  revalidateTag: mocks.revalidateTag,
}));

vi.mock('@/lib/answer-cache', () => ({
  answerCacheTag: (question: string) => `answer:${question}`,
  getCachedAnswer: mocks.getCachedAnswer,
}));

import { POST } from './route';

describe('POST /api/ask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reads the answer cache before doing any upstream work', async () => {
    const answer = {
      kind: 'react_answer' as const,
      message: 'A cached answer',
      sources: [],
    };
    mocks.getCachedAnswer.mockResolvedValue(answer);

    const response = await POST(
      new Request('http://localhost/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: '  How does useState work?  ' }),
      }),
    );
    const events = (await response.text())
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line));

    expect(mocks.getCachedAnswer).toHaveBeenCalledWith('How does useState work?');
    expect(events).toEqual([
      {
        type: 'status',
        stage: 'cache',
        message: 'Checking saved React answers',
      },
      { type: 'result', data: answer },
    ]);
  });

  it('replaces a long-running cache status while a fresh answer is prepared', async () => {
    vi.useFakeTimers();
    const answer = {
      kind: 'react_answer' as const,
      message: 'A fresh answer',
      sources: [],
    };
    let resolveAnswer: ((value: typeof answer) => void) | undefined;
    mocks.getCachedAnswer.mockReturnValue(
      new Promise((resolve) => {
        resolveAnswer = resolve;
      }),
    );

    const response = await POST(
      new Request('http://localhost/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: 'How does Suspense work?' }),
      }),
    );
    const body = response.text();

    await vi.advanceTimersByTimeAsync(500);
    resolveAnswer?.(answer);
    const events = (await body)
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line));

    expect(events).toEqual([
      {
        type: 'status',
        stage: 'cache',
        message: 'Checking saved React answers',
      },
      {
        type: 'status',
        stage: 'answering',
        message: 'Checking question scope and preparing an answer',
      },
      { type: 'result', data: answer },
    ]);
  });
});
