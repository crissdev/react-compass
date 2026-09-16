export function normalizeQuestion(question: string): string {
  return question.trim().replace(/\s+/g, ' ');
}

export function questionKey(question: string): string {
  return normalizeQuestion(question).toLowerCase();
}
