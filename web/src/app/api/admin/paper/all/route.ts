import { type NextRequest } from 'next/server';
import { GET as papersListGet } from '../../papers_list/route';

export async function GET(request: NextRequest) {
  return papersListGet(request);
}
