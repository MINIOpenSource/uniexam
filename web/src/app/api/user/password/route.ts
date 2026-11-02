import { type NextRequest, NextResponse } from 'next/server';
import type { UserPasswordUpdate } from '@/types/auth';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function PUT(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const passwordData: UserPasswordUpdate = await request.json();
    const backendResponse = await fetch(`${BACKEND_URL}/users/me/password`, {
      method: 'PUT',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(passwordData),
    });

    if (backendResponse.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY PUT /api/user/password ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during password update proxy' }, { status: 500 });
  }
}
