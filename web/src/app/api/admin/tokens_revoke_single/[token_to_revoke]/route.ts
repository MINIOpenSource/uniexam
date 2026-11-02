import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: { token_to_revoke: string };
}

export async function DELETE(request: NextRequest, context: Context) {
  const { token_to_revoke } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const adminToken = extractBearerTokenFromRequest(request);
  if (!adminToken) {
    return NextResponse.json({ detail: 'Admin token is required in Authorization header' }, { status: 401 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/tokens/${encodeURIComponent(token_to_revoke)}`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'DELETE',
      headers: buildBackendAuthHeaders(adminToken),
    });
    if (backendResponse.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await backendResponse.json().catch(() => null);
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY DELETE /api/admin/tokens_revoke_single ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during single token revocation' }, { status: 500 });
  }
}
