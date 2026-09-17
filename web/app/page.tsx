import { Suspense } from 'react';
import { DocChat } from '@/components/doc-chat';
import { normalizeQuestion } from '@/lib/questions';

type HomeProps = {
  searchParams: Promise<{ q?: string | string[] }>;
};

async function DocChatFromQuery({ searchParams }: HomeProps) {
  const query = await searchParams;
  const question = typeof query.q === 'string' ? normalizeQuestion(query.q) : '';
  const hasQuestion = question.length >= 2 && question.length <= 1_000;

  return (
    <DocChat
      key={hasQuestion ? question : 'dashboard'}
      initialQuestion={hasQuestion ? question : ''}
    />
  );
}

export default function Home({ searchParams }: HomeProps) {
  return (
    <Suspense
      fallback={
        <main className="question-route-loading" role="status">
          Loading question…
        </main>
      }
    >
      <DocChatFromQuery searchParams={searchParams} />
    </Suspense>
  );
}
