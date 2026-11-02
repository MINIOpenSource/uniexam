import { type NextRequest, NextResponse } from 'next/server';
import type { SettingsUpdatePayload } from '@/types/admin';
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

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/settings`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/admin/settings ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during admin settings fetch proxy' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const settingsPayload: SettingsUpdatePayload = await request.json();
    const backendApiUrl = new URL(`${BACKEND_URL}/admin/settings`);

    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'POST',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(settingsPayload),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY POST /api/admin/settings ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during admin settings update proxy' }, { status: 500 });
  }
}
