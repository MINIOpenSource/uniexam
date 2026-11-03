import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: Promise<{ paper_id: string }>;
}

export async function GET(request: NextRequest, context: Context) {
  const { paper_id } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/grading/papers/${encodeURIComponent(paper_id)}/subjective-questions`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY GET /api/admin/grading/papers/${paper_id}/subjective_questions ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during subjective questions fetch' }, { status: 500 });
  }
}
