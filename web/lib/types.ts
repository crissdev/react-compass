export type SourceExcerpt = {
  id: string;
  citation: number;
  title: string;
  section: string | null;
  source_type: 'reference' | 'learn' | 'blog' | 'github' | 'unknown';
  source_url: string;
  excerpt: string;
};

export type Answer = {
  message: string;
  sources: SourceExcerpt[];
};

export type StreamEvent =
  | { type: 'status'; stage: string; message: string }
  | { type: 'result'; data: Answer }
  | { type: 'error'; message: string };
