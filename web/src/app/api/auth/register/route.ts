
// This proxy route should now point to POST /auth/signin
import { type NextRequest, NextResponse } from 'next/server';
import type { UserCreatePayload } from '@/types/auth';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

export async function POST(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  try {
    const body: UserCreatePayload = await request.json();
    // Backend /auth/signin expects UserCreatePayload directly as JSON
    const backendResponse = await fetch(`${BACKEND_URL}/auth/signin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body), // Forward the payload as is
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY POST /api/auth/register (now signin) ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during registration proxy' }, { status: 500 });
  }
}
