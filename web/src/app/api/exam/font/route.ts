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
    const payload = await request.json();
    const backendResponse = await fetch(`${BACKEND_URL}/exam/font`, {
      method: 'POST',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });

    if (!backendResponse.ok) {
      const errData = await backendResponse.json().catch(() => ({ detail: 'Font request failed' }));
      return NextResponse.json(errData, { status: backendResponse.status });
    }

    const arrayBuffer = await backendResponse.arrayBuffer();
    return new NextResponse(arrayBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'font/ttf',
        'Cache-Control': 'private, no-store',
      },
    });
  } catch (error) {
    console.error('[API PROXY POST /api/exam/font ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during font fetch proxy' }, { status: 500 });
  }
}
