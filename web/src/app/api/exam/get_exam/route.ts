import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function GET(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const difficulty = searchParams.get('difficulty');
  const num_questions = searchParams.get('num_questions');

  const backendApiUrl = new URL(`${BACKEND_URL}/get_exam`);
  if (difficulty) backendApiUrl.searchParams.append('difficulty', difficulty);
  if (num_questions) backendApiUrl.searchParams.append('num_questions', num_questions);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/exam/get_exam ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during exam start proxy' }, { status: 500 });
  }
}
