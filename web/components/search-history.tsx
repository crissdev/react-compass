import { Clock3, History as HistoryIcon, Trash2 } from 'lucide-react';
import type { SearchHistoryItem } from '@/lib/search-history';

const historyDateFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
});

function formatHistoryDate(timestamp: number): string {
  const elapsedMinutes = Math.floor((Date.now() - timestamp) / 60_000);
  if (elapsedMinutes < 1) return 'Just now';
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`;
  if (elapsedMinutes < 1_440) return `${Math.floor(elapsedMinutes / 60)}h ago`;
  return historyDateFormatter.format(timestamp);
}

type SearchHistoryProps = {
  items: SearchHistoryItem[];
  removingQuestion: string | null;
  onSelect: (question: string) => void;
  onRemove: (question: string) => void;
};

export function SearchHistory({
  items,
  removingQuestion,
  onSelect,
  onRemove,
}: SearchHistoryProps) {
  if (items.length === 0) return null;

  return (
    <section className="search-history" aria-labelledby="search-history-heading">
      <div className="search-history-heading">
        <div>
          <HistoryIcon size={15} aria-hidden="true" />
          <h2 id="search-history-heading">Search history</h2>
        </div>
      </div>
      <ul>
        {items.map((item) => (
          <li key={item.question.toLowerCase()}>
            <button
              className="history-question"
              type="button"
              onClick={() => onSelect(item.question)}
            >
              <Clock3 size={15} aria-hidden="true" />
              <span>
                <strong>{item.question}</strong>
                <small>{formatHistoryDate(item.askedAt)}</small>
              </span>
            </button>
            <button
              className="history-remove"
              type="button"
              onClick={() => onRemove(item.question)}
              disabled={removingQuestion === item.question}
              aria-label={`Remove “${item.question}” from search history`}
              title="Remove from history and clear its cached answer"
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
