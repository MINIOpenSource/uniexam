import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function GET(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ message: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ message: 'Unauthorized: Missing or malformed token for admin route' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const paper_id = searchParams.get('paper_id');
  if (!paper_id) {
    return NextResponse.json({ message: 'Bad Request: Missing paper_id' }, { status: 400 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/papers/${encodeURIComponent(paper_id)}`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/admin/paper ERROR]', error);
    return NextResponse.json({ message: 'Internal Server Error during admin paper detail fetch proxy' }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ message: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ message: 'Unauthorized: Missing or malformed token for admin route' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const paper_id = searchParams.get('paper_id');
  if (!paper_id) {
    return NextResponse.json({ message: 'Bad Request: Missing paper_id' }, { status: 400 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/papers/${encodeURIComponent(paper_id)}`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'DELETE',
      headers: buildBackendAuthHeaders(token),
    });
    if (backendResponse.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await backendResponse.json().catch(() => ({}));
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY DELETE /api/admin/paper ERROR]', error);
    return NextResponse.json({ message: 'Internal Server Error during admin paper delete proxy' }, { status: 500 });
  }
}
