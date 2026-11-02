import { type NextRequest } from 'next/server';
import { GET as usersListGet } from '../users_list/route';

export async function GET(request: NextRequest) {
  return usersListGet(request);
}
