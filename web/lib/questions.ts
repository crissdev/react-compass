export function normalizeQuestion(question: string): string {
  return question.trim().replace(/\s+/g, ' ');
}

export function questionKey(question: string): string {
  return normalizeQuestion(question).toLowerCase();
}

export function questionHref(question: string): string {
  const normalized = normalizeQuestion(question);
  const params = new URLSearchParams({ q: normalized });
  return `/?${params.toString()}`;
}
