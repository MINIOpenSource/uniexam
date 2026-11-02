import { type NextRequest, NextResponse } from 'next/server';
import type { GradeSubmissionPayload } from '@/types/admin';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: {
    paper_id: string;
    question_internal_id: string;
  };
}

export async function POST(request: NextRequest, context: Context) {
  const { paper_id, question_internal_id } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const payload: GradeSubmissionPayload = await request.json();
    const backendApiUrl = new URL(`${BACKEND_URL}/admin/grading/papers/${encodeURIComponent(paper_id)}/questions/${encodeURIComponent(question_internal_id)}/grade`);

    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'POST',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });

    if (backendResponse.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await backendResponse.json().catch(() => null);
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY POST /api/admin/grading/papers/.../grade ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during grade submission' }, { status: 500 });
  }
}
