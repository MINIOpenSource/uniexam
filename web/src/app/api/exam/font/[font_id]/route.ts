import { type NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ font_id: string }> }
) {
  if (!BACKEND_URL) {
    return new NextResponse('Backend URL not configured', { status: 500 });
  }
  const { font_id } = await context.params;
  if (!font_id) {
    return new NextResponse('Missing font_id', { status: 400 });
  }

  try {
    const backendResponse = await fetch(
      `${BACKEND_URL}/exam/font/${encodeURIComponent(font_id)}`,
      { method: 'GET' }
    );
    if (!backendResponse.ok) {
      return new NextResponse('Font not found', { status: backendResponse.status });
    }
    const arrayBuffer = await backendResponse.arrayBuffer();
    return new NextResponse(arrayBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'font/ttf',
        'Cache-Control': 'private, max-age=3600',
      },
    });
  } catch (error) {
    console.error('[API PROXY GET /api/exam/font ERROR]', error);
    return new NextResponse('Internal Server Error', { status: 500 });
  }
}
