import { type NextRequest, NextResponse } from 'next/server';
import type { UserProfileUpdate } from '@/types/auth';
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

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/users/me`, {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/user/profile ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during profile fetch proxy' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const profileData: UserProfileUpdate = await request.json();
    const backendResponse = await fetch(`${BACKEND_URL}/users/me`, {
      method: 'PUT',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(profileData),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY PUT /api/user/profile ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during profile update proxy' }, { status: 500 });
  }
}
