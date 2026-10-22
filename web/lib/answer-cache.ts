import { Buffer } from 'node:buffer';
import type { Answer } from '@/lib/types';
import { normalizeQuestion, questionKey } from '@/lib/questions';

const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_CACHE_ENTRIES = 256;
const MAX_CACHE_BYTES = 8 * 1024 * 1024;

type CacheEntry = {
  serializedAnswer: string;
  expiresAt: number;
  bytes: number;
};

// Store only completed answers. Active requests keep their own cancellation and
// progress state, so one caller cannot interrupt another caller's search.
const answers = new Map<string, CacheEntry>();
let cachedBytes = 0;

function removeEntry(key: string): void {
  const entry = answers.get(key);
  if (!entry) return;
  cachedBytes -= entry.bytes;
  answers.delete(key);
}

export function getCachedAnswer(question: string): Answer | undefined {
  const key = normalizeQuestion(question);
  const entry = answers.get(key);
  if (!entry) return undefined;
  if (entry.expiresAt <= Date.now()) {
    removeEntry(key);
    return undefined;
  }

  // Map insertion order tracks least recently used entries without extending TTL.
  answers.delete(key);
  answers.set(key, entry);
  return JSON.parse(entry.serializedAnswer) as Answer;
}

export function cacheAnswer(question: string, answer: Answer): void {
  if (answer.kind !== 'react_answer') return;

  const key = normalizeQuestion(question);
  const serializedAnswer = JSON.stringify(answer);
  const bytes = Buffer.byteLength(key) + Buffer.byteLength(serializedAnswer);
  if (bytes > MAX_CACHE_BYTES) return;

  const now = Date.now();
  for (const [cachedKey, entry] of answers) {
    if (entry.expiresAt <= now) removeEntry(cachedKey);
  }
  removeEntry(key);

  while (
    answers.size >= MAX_CACHE_ENTRIES ||
    cachedBytes + bytes > MAX_CACHE_BYTES
  ) {
    const oldestKey = answers.keys().next().value;
    if (oldestKey === undefined) break;
    removeEntry(oldestKey);
  }

  answers.set(key, {
    serializedAnswer,
    bytes,
    expiresAt: now + CACHE_TTL_MS,
  });
  cachedBytes += bytes;
}

export function invalidateCachedAnswer(question: string): void {
  const invalidatedKey = questionKey(question);
  for (const key of answers.keys()) {
    if (questionKey(key) === invalidatedKey) removeEntry(key);
  }
}
