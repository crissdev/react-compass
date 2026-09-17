export function normalizeQuestion(question: string): string {
  return question.trim().replace(/\s+/g, ' ');
}

export function questionKey(question: string): string {
  return normalizeQuestion(question).toLowerCase();
}

export function questionSlug(question: string): string {
  const slug = normalizeQuestion(question)
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
    .replace(/-+$/g, '');

  return slug || 'question';
}

export function questionHref(question: string): string {
  const normalized = normalizeQuestion(question);
  const params = new URLSearchParams({ q: normalized });
  return `/questions/${questionSlug(normalized)}?${params.toString()}`;
}
