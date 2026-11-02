import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function POST(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const submission = await request.json();
    const backendResponse = await fetch(`${BACKEND_URL}/finish`, {
      method: 'POST',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(submission),
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY POST /api/exam/finish ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during exam finish proxy' }, { status: 500 });
  }
}
