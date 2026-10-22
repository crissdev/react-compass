import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Answer } from './types';

const DAY_MS = 24 * 60 * 60 * 1000;
const answer: Answer = {
  kind: 'react_answer',
  message: 'State lets a component remember information.',
  sources: [],
};

let cache: typeof import('./answer-cache');

describe('completed answer cache', () => {
  beforeEach(async () => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-22T12:00:00Z'));
    cache = await import('./answer-cache');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns a miss without making an upstream request', () => {
    expect(cache.getCachedAnswer('How does useState work?')).toBeUndefined();
  });

  it('reuses completed answers for the same normalized question', () => {
    cache.cacheAnswer('  How  does useState work?  ', answer);

    expect(cache.getCachedAnswer('How does useState work?')).toEqual(answer);
    expect(cache.getCachedAnswer('How does useEffect work?')).toBeUndefined();
  });

  it('keeps differently cased code in separate cache entries', () => {
    const otherAnswer = {
      ...answer,
      message: 'Use the capitalized component.',
    };
    cache.cacheAnswer('Why does <button /> work?', answer);
    cache.cacheAnswer('Why does <Button /> work?', otherAnswer);

    expect(cache.getCachedAnswer('Why does <button /> work?')).toEqual(answer);
    expect(cache.getCachedAnswer('Why does <Button /> work?')).toEqual(
      otherAnswer,
    );
  });

  it.each(['no_match', 'scope_notice'] as const)(
    'does not store %s responses',
    (kind) => {
      cache.cacheAnswer('An unrelated question', { ...answer, kind });

      expect(cache.getCachedAnswer('An unrelated question')).toBeUndefined();
    },
  );

  it('isolates stored answers from mutations by callers', () => {
    const original = { ...answer };
    cache.cacheAnswer('How does useState work?', original);
    original.message = 'Changed after storage';

    const retrieved = cache.getCachedAnswer('How does useState work?');
    expect(retrieved).toEqual(answer);
    retrieved!.message = 'Changed after retrieval';
    expect(cache.getCachedAnswer('How does useState work?')).toEqual(answer);
  });

  it('expires seven days after storage even when read shortly before expiry', () => {
    cache.cacheAnswer('How does useState work?', answer);
    vi.advanceTimersByTime(7 * DAY_MS - 1);
    expect(cache.getCachedAnswer('How does useState work?')).toEqual(answer);

    vi.advanceTimersByTime(1);
    expect(cache.getCachedAnswer('How does useState work?')).toBeUndefined();
  });

  it('replaces an answer and starts a new expiry period', () => {
    cache.cacheAnswer('How does useState work?', answer);
    vi.advanceTimersByTime(6 * DAY_MS);
    const replacement = { ...answer, message: 'Updated documentation answer.' };
    cache.cacheAnswer('How does useState work?', replacement);
    vi.advanceTimersByTime(DAY_MS);

    expect(cache.getCachedAnswer('How does useState work?')).toEqual(
      replacement,
    );
  });

  it('evicts the least recently used answer above 256 entries', () => {
    for (let index = 0; index < 256; index += 1) {
      cache.cacheAnswer(`Question ${index}`, answer);
    }
    cache.getCachedAnswer('Question 0');
    cache.cacheAnswer('Question 256', answer);

    expect(cache.getCachedAnswer('Question 0')).toEqual(answer);
    expect(cache.getCachedAnswer('Question 1')).toBeUndefined();
    expect(cache.getCachedAnswer('Question 255')).toEqual(answer);
    expect(cache.getCachedAnswer('Question 256')).toEqual(answer);
  });

  it('evicts least recently used answers when total payload exceeds 8 MiB', () => {
    const largeAnswer = { ...answer, message: 'a'.repeat(3 * 1024 * 1024) };
    cache.cacheAnswer('Question 0', largeAnswer);
    cache.cacheAnswer('Question 1', largeAnswer);
    cache.getCachedAnswer('Question 0');
    cache.cacheAnswer('Question 2', largeAnswer);

    expect(cache.getCachedAnswer('Question 0')).toEqual(largeAnswer);
    expect(cache.getCachedAnswer('Question 1')).toBeUndefined();
    expect(cache.getCachedAnswer('Question 2')).toEqual(largeAnswer);
  });

  it('measures payload size in bytes and skips oversized answers', () => {
    cache.cacheAnswer('Small answer', answer);
    cache.cacheAnswer('Oversized answer', {
      ...answer,
      message: 'é'.repeat(4 * 1024 * 1024),
    });

    expect(cache.getCachedAnswer('Oversized answer')).toBeUndefined();
    expect(cache.getCachedAnswer('Small answer')).toEqual(answer);
  });

  it('reclaims expired payloads before evicting fresh answers', () => {
    const largeAnswer = { ...answer, message: 'a'.repeat(3 * 1024 * 1024) };
    cache.cacheAnswer('Expiring answer', largeAnswer);
    vi.advanceTimersByTime(DAY_MS);
    cache.cacheAnswer('Fresh answer', largeAnswer);
    cache.getCachedAnswer('Expiring answer');
    vi.advanceTimersByTime(6 * DAY_MS);
    cache.cacheAnswer('New answer', largeAnswer);

    expect(cache.getCachedAnswer('Expiring answer')).toBeUndefined();
    expect(cache.getCachedAnswer('Fresh answer')).toEqual(largeAnswer);
    expect(cache.getCachedAnswer('New answer')).toEqual(largeAnswer);
  });

  it('invalidates every case variant while retaining unrelated answers', () => {
    cache.cacheAnswer('How does useState work?', answer);
    cache.cacheAnswer('HOW DOES USESTATE WORK?', answer);
    cache.cacheAnswer('How does useEffect work?', answer);

    cache.invalidateCachedAnswer('  how  does usestate work?  ');

    expect(cache.getCachedAnswer('How does useState work?')).toBeUndefined();
    expect(cache.getCachedAnswer('HOW DOES USESTATE WORK?')).toBeUndefined();
    expect(cache.getCachedAnswer('How does useEffect work?')).toEqual(answer);
  });

  it('releases payload accounting after replacements and invalidations', () => {
    const largeAnswer = { ...answer, message: 'a'.repeat(3 * 1024 * 1024) };
    cache.cacheAnswer('Replaced answer', largeAnswer);
    cache.cacheAnswer('Replaced answer', answer);
    cache.cacheAnswer('Invalidated answer', largeAnswer);
    cache.invalidateCachedAnswer('Invalidated answer');
    cache.cacheAnswer('Large answer 1', largeAnswer);
    cache.cacheAnswer('Large answer 2', largeAnswer);

    expect(cache.getCachedAnswer('Replaced answer')).toEqual(answer);
    expect(cache.getCachedAnswer('Large answer 1')).toEqual(largeAnswer);
    expect(cache.getCachedAnswer('Large answer 2')).toEqual(largeAnswer);
  });
});
