import { normalizeQuestion, questionKey } from './questions';

export type SearchHistoryItem = {
  question: string;
  askedAt: number;
};

export const SEARCH_HISTORY_LIMIT = 15;
export const SEARCH_HISTORY_STORAGE_KEY = 'docchat-search-history';

function isSearchHistoryItem(value: unknown): value is SearchHistoryItem {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<SearchHistoryItem>;
  return typeof item.question === 'string' && typeof item.askedAt === 'number';
}

export function parseSearchHistory(value: string | null): SearchHistoryItem[] {
  if (!value) return [];

  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isSearchHistoryItem).slice(0, SEARCH_HISTORY_LIMIT);
  } catch {
    return [];
  }
}

export function addSearchHistoryItem(
  items: readonly SearchHistoryItem[],
  question: string,
  askedAt = Date.now(),
): SearchHistoryItem[] {
  const normalized = normalizeQuestion(question);
  if (normalized.length < 2) return [...items];

  const key = questionKey(normalized);
  return [
    { question: normalized, askedAt },
    ...items.filter((item) => questionKey(item.question) !== key),
  ].slice(0, SEARCH_HISTORY_LIMIT);
}

export function removeSearchHistoryItem(
  items: readonly SearchHistoryItem[],
  question: string,
): SearchHistoryItem[] {
  const key = questionKey(question);
  return items.filter((item) => questionKey(item.question) !== key);
}
