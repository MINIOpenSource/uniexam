import { type NextRequest } from 'next/server';
import { GET as userDetailGet } from '../../users_detail/[uid]/route';
import { PUT as userUpdatePut } from '../../users_update/[uid]/route';

interface Context {
  params: { uid: string };
}

export async function GET(request: NextRequest, context: Context) {
  return userDetailGet(request, context);
}

export async function PUT(request: NextRequest, context: Context) {
  return userUpdatePut(request, context);
}
