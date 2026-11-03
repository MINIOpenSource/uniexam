import { type NextRequest, NextResponse } from 'next/server';
import type { AdminUserUpdate } from '@/types/auth';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: Promise<{ uid: string }>;
}

export async function PUT(request: NextRequest, context: Context) {
  const { uid: user_uid } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  try {
    const payload: AdminUserUpdate = await request.json();
    const backendApiUrl = new URL(`${BACKEND_URL}/admin/users/${encodeURIComponent(user_uid)}`);

    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'PUT',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY PUT /api/admin/users_update/${user_uid} ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during admin user update proxy' }, { status: 500 });
  }
}
