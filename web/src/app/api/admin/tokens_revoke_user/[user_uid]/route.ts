import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: Promise<{ user_uid: string }>;
}

export async function DELETE(request: NextRequest, context: Context) {
  const { user_uid } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/tokens/user/${encodeURIComponent(user_uid)}`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'DELETE',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY DELETE /api/admin/tokens_revoke_user/${user_uid} ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during user token revocation' }, { status: 500 });
  }
}
