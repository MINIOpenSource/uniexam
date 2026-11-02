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
  const paperId = searchParams.get('paper_id');
  if (!paperId) {
    return NextResponse.json({ detail: 'Bad Request: Missing paper_id' }, { status: 400 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/history_paper`);
  backendApiUrl.searchParams.append('paper_id', paperId);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/history/paper ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during history paper details proxy' }, { status: 500 });
  }
}
