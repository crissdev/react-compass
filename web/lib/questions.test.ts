import { describe, expect, it } from 'vitest';
import { questionHref } from './questions';

describe('question URLs', () => {
  it('preserves the exact normalized question in the dashboard query string', () => {
    expect(questionHref('  How does   useState work?  ')).toBe(
      '/?q=How+does+useState+work%3F',
    );
  });
});
