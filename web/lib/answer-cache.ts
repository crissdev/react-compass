import { createHash } from 'node:crypto';
import { cacheLife, cacheTag } from 'next/cache';
import { classifyQuestion } from '@/lib/question-gate';
import type { Answer } from '@/lib/types';
import { normalizeQuestion, questionKey } from '@/lib/questions';

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';

export function answerCacheTag(question: string): string {
  const digest = createHash('sha256').update(questionKey(question)).digest('hex');
  return `docchat-answer:${digest}`;
}

export async function getCachedAnswer(question: string): Promise<Answer> {
  'use cache';

  cacheTag(answerCacheTag(question));

  const gate = await classifyQuestion(question);
  if (gate.category !== 'react') {
    if (!gate.response) throw new Error('The question gate returned an invalid response.');
    cacheLife({ stale: 0, revalidate: 0, expire: 1 });
    return gate.response;
  }

  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: normalizeQuestion(question) }),
    cache: 'no-store',
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'The documentation API returned an error.');
  }

  const answer = (await response.json()) as Answer;
  if (answer.kind === 'react_answer') {
    cacheLife('weeks');
  } else {
    cacheLife({ stale: 0, revalidate: 0, expire: 1 });
  }

  return answer;
}
