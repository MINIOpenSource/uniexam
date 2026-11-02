import { type NextRequest } from 'next/server';
import { GET as getExamGet } from '../get_exam/route';

export async function GET(request: NextRequest) {
  return getExamGet(request);
}
