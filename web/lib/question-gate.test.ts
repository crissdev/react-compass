import { afterEach, describe, expect, it, vi } from 'vitest';
import { classifyQuestion } from './question-gate';

describe('classifyQuestion', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('always calls the classification endpoint without a Next.js fetch cache', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        category: 'unrelated',
        response: {
          kind: 'scope_notice',
          message: 'React questions only.',
          sources: [],
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await classifyQuestion('  What is the capital of France?  ');

    expect(result.category).toBe('unrelated');
    expect(result.response?.kind).toBe('scope_notice');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/classify',
      expect.objectContaining({
        body: JSON.stringify({ question: 'What is the capital of France?' }),
        cache: 'no-store',
        method: 'POST',
      }),
    );
  });
});
