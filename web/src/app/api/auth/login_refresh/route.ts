import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function GET(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const oldToken = extractBearerTokenFromRequest(request);
  if (!oldToken) {
    return NextResponse.json({ detail: 'Token required in Authorization header' }, { status: 401 });
  }

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/auth/login`, {
      method: 'GET',
      headers: buildBackendAuthHeaders(oldToken),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/auth/login_refresh ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during token refresh proxy' }, { status: 500 });
  }
}
