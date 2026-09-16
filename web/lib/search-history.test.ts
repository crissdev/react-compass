import { describe, expect, it } from 'vitest';
import {
  addSearchHistoryItem,
  parseSearchHistory,
  removeSearchHistoryItem,
  SEARCH_HISTORY_LIMIT,
} from './search-history';

describe('search history', () => {
  it('adds normalized questions newest first and de-duplicates equivalent entries', () => {
    const first = addSearchHistoryItem([], '  How does   useState work?  ', 10);
    const second = addSearchHistoryItem(first, 'how does useState work?', 20);

    expect(second).toEqual([{ question: 'how does useState work?', askedAt: 20 }]);
  });

  it('keeps only the latest questions', () => {
    const items = Array.from({ length: SEARCH_HISTORY_LIMIT + 2 }, (_, index) => ({
      question: `Question ${index}`,
      askedAt: index,
    }));

    const result = addSearchHistoryItem(items, 'Newest question', 100);

    expect(result).toHaveLength(SEARCH_HISTORY_LIMIT);
    expect(result[0].question).toBe('Newest question');
    expect(result.at(-1)?.question).toBe(`Question ${SEARCH_HISTORY_LIMIT - 2}`);
  });

  it('removes matching questions without affecting the others', () => {
    const items = [
      { question: 'What is useEffect?', askedAt: 2 },
      { question: 'What is useMemo?', askedAt: 1 },
    ];

    expect(removeSearchHistoryItem(items, ' what is useeffect? ')).toEqual([items[1]]);
  });

  it('ignores invalid persisted history', () => {
    expect(parseSearchHistory('not json')).toEqual([]);
    expect(parseSearchHistory('{"question":"no array"}')).toEqual([]);
    expect(
      parseSearchHistory('[{"question":"Valid","askedAt":1},{"question":2,"askedAt":1}]'),
    ).toEqual([{ question: 'Valid', askedAt: 1 }]);
  });
});
