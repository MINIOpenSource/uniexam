import { type NextRequest, NextResponse } from 'next/server';
import { GET as loginRefreshGet } from '../login_refresh/route';

export async function GET(request: NextRequest) {
  return loginRefreshGet(request);
}
