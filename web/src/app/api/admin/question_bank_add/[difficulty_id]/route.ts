import { type NextRequest, NextResponse } from 'next/server';
import type { QuestionModel } from '@/types/admin';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: Promise<{ difficulty_id: string }>;
}

export async function POST(request: NextRequest, context: Context) {
  const { difficulty_id } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const questionPayload: QuestionModel = await request.json();
    const backendApiUrl = new URL(`${BACKEND_URL}/admin/question-banks/${encodeURIComponent(difficulty_id)}/questions`);

    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'POST',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(questionPayload),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY POST /api/admin/question_bank_add/${difficulty_id} ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during admin question add proxy' }, { status: 500 });
  }
}
