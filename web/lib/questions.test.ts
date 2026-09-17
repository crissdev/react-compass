import { describe, expect, it } from 'vitest';
import { questionHref, questionSlug } from './questions';

describe('question URLs', () => {
  it('creates a readable slug and preserves the exact normalized question', () => {
    expect(questionHref('  How does   useState work?  ')).toBe(
      '/questions/how-does-usestate-work?q=How+does+useState+work%3F',
    );
  });

  it('removes accents and limits long slugs', () => {
    expect(questionSlug('¿Cómo funciona React?')).toBe('como-funciona-react');
    expect(questionSlug('a'.repeat(100))).toHaveLength(80);
  });
});
