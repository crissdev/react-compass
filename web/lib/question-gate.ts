import { normalizeQuestion } from '@/lib/questions';
import type { Answer } from '@/lib/types';

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';

export type QuestionGate = {
  category: 'react' | 'unrelated' | 'prompt_injection';
  response: Answer | null;
};

export async function classifyQuestion(question: string): Promise<QuestionGate> {
  const response = await fetch(`${API_BASE_URL}/classify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: normalizeQuestion(question) }),
    cache: 'no-store',
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'The documentation API could not classify the question.');
  }

  return (await response.json()) as QuestionGate;
}
