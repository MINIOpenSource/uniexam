import { type NextRequest, NextResponse } from 'next/server';
import { extractBearerTokenFromRequest, buildBackendAuthHeaders } from '@/lib/proxy-auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

interface Context {
  params: Promise<{ difficulty_id: string }>;
}

export async function DELETE(request: NextRequest, context: Context) {
  const { difficulty_id } = await context.params;
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ detail: 'Token is required in Authorization header' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const index = searchParams.get('index');
  if (index === null) {
    return NextResponse.json({ detail: 'Bad Request: Missing index' }, { status: 400 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/question-banks/${encodeURIComponent(difficulty_id)}/questions`);
  backendApiUrl.searchParams.append('index', index);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'DELETE',
      headers: buildBackendAuthHeaders(token),
    });
    if (backendResponse.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const data = await backendResponse.json().catch(() => null);
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error(`[API PROXY DELETE /api/admin/question_bank_delete/${difficulty_id} ERROR]`, error);
    return NextResponse.json({ detail: 'Internal Server Error during admin question delete proxy' }, { status: 500 });
  }
}
