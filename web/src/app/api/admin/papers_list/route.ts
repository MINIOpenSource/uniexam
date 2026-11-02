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
  const backendApiUrl = new URL(`${BACKEND_URL}/admin/papers`);
  searchParams.forEach((value, key) => {
    if (key !== 'token') {
      backendApiUrl.searchParams.append(key, value);
    }
  });

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });

    const format = searchParams.get('format');
    if (format && (format === 'csv' || format === 'xlsx') && backendResponse.ok) {
      const blob = await backendResponse.blob();
      const headers = new Headers(backendResponse.headers);
      return new NextResponse(blob, { status: backendResponse.status, statusText: backendResponse.statusText, headers });
    }

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/admin/papers_list ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during admin papers fetch proxy' }, { status: 500 });
  }
}
