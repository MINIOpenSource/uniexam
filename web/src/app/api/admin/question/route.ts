import { type NextRequest, NextResponse } from 'next/server';
import type { QuestionModel } from '@/types/admin';
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
  const difficulty = searchParams.get('difficulty');
  if (!difficulty) {
    return NextResponse.json({ message: 'Bad Request: Missing difficulty' }, { status: 400 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/question-banks/${encodeURIComponent(difficulty)}/content`);

  try {
    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'GET',
      headers: buildBackendAuthHeaders(token),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/admin/question ERROR]', error);
    return NextResponse.json({ message: 'Internal Server Error during admin question bank fetch proxy' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ message: 'Backend URL not configured' }, { status: 500 });
  }
  const token = extractBearerTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ message: 'Unauthorized: Missing or malformed token for admin route' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const difficulty = searchParams.get('difficulty');
  if (!difficulty) {
    return NextResponse.json({ message: 'Bad Request: Missing difficulty' }, { status: 400 });
  }

  try {
    const questionPayload: QuestionModel = await request.json();
    const backendApiUrl = new URL(`${BACKEND_URL}/admin/question-banks/${encodeURIComponent(difficulty)}/questions`);

    const backendResponse = await fetch(backendApiUrl.toString(), {
      method: 'POST',
      headers: buildBackendAuthHeaders(token, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(questionPayload),
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY POST /api/admin/question ERROR]', error);
    return NextResponse.json({ message: 'Internal Server Error during admin question add proxy' }, { status: 500 });
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
  const difficulty = searchParams.get('difficulty');
  const index = searchParams.get('index');
  if (!difficulty || index === null) {
    return NextResponse.json({ message: 'Bad Request: Missing difficulty or index' }, { status: 400 });
  }

  const backendApiUrl = new URL(`${BACKEND_URL}/admin/question-banks/${encodeURIComponent(difficulty)}/questions`);
  backendApiUrl.searchParams.append('index', index);

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
    console.error('[API PROXY DELETE /api/admin/question ERROR]', error);
    return NextResponse.json({ message: 'Internal Server Error during admin question delete proxy' }, { status: 500 });
  }
}
