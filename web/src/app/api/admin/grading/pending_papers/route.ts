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
  const skip = searchParams.get('skip') || '0';
  const limit = searchParams.get('limit') || '100';

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/grading/pending-papers`);
  backendApiUrl.searchParams.append('skip', skip);
  backendApiUrl.searchParams.append('limit', limit);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/admin/grading/pending_papers ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during pending papers fetch' }, { status: 500 });
  }
}
