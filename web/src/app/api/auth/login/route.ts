
import { type NextRequest, NextResponse } from 'next/server';
import type { UserCreatePayload } from '@/types/auth'; // Keep for frontend structure to proxy

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

// POST /auth/login (v3.0.0) - Backend expects application/x-www-form-urlencoded
export async function POST(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: 'Backend URL not configured' }, { status: 500 });
  }
  try {
    const body: UserCreatePayload = await request.json(); // Frontend sends JSON

    // Transform JSON to application/x-www-form-urlencoded for the backend
    const formData = new URLSearchParams();
    formData.append('username', body.uid); // Backend 'username' maps to frontend 'uid'
    if (body.password) {
      formData.append('password', body.password);
    }
    // Nickname, email, qq are not part of the login form data for the backend's /auth/login

    const backendResponse = await fetch(`${BACKEND_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString(),
    });

    const data = await backendResponse.json();
    // Pass through backend's status and response
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    console.error('[API PROXY POST /api/auth/login ERROR]', error);
    return NextResponse.json({ detail: 'Internal Server Error during login proxy' }, { status: 500 });
  }
}
