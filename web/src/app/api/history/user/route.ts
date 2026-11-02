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
  const format = searchParams.get('format');

  const backendApiUrl = new URL(`${BACKEND_URL}/history`);
  if (format) {
    backendApiUrl.searchParams.append('format', format);
  }

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    if (format && backendResponse.ok) {
      const blob = await backendResponse.blob();
      const headers = new Headers(backendResponse.headers);
      return new NextResponse(blob, { status: backendResponse.status, statusText: backendResponse.statusText, headers });
    }
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error: any) {
    console.error('[API PROXY GET /api/history/user ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error: Failed to connect to backend service for user history.' }, { status: 500 });
  }
}
