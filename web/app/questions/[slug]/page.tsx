import { notFound } from 'next/navigation';
import { DocChat } from '@/components/doc-chat';
import { normalizeQuestion, questionSlug } from '@/lib/questions';

type QuestionPageProps = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ q?: string | string[] }>;
};

export default async function QuestionPage({ params, searchParams }: QuestionPageProps) {
  const [{ slug }, query] = await Promise.all([params, searchParams]);
  const question = typeof query.q === 'string' ? normalizeQuestion(query.q) : '';

  if (question.length < 2 || question.length > 1_000 || questionSlug(question) !== slug) {
    notFound();
  }

  return <DocChat key={question} initialQuestion={question} showDashboardLink />;
}
