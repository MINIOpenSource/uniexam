
import { type NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

// GET /users/directory (v3.0.0 Public API)
export async function GET(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/users/directory`, {
      method: 'GET',
      cache: 'no-store', // Or configure revalidation
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY GET /api/public/users_directory ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during user directory fetch proxy' }, { status: 500 });
  }
}
