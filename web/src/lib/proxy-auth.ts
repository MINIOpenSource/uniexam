import { type NextRequest } from 'next/server';

export function extractBearerTokenFromRequest(request: NextRequest): string | null {
  const authHeader = request.headers.get('Authorization') || request.headers.get('X-Access-Token');
  if (!authHeader) return null;
  const trimmed = authHeader.trim();
  if (trimmed.toLowerCase().startsWith('bearer ')) {
    const tok = trimmed.slice(7).trim();
    return tok || null;
  }
  return trimmed || null;
}

export function buildBackendAuthHeaders(token: string, extra?: Record<string, string>): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    ...extra,
  };
}
