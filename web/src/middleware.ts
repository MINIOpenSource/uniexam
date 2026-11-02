
import { NextRequest, NextResponse } from 'next/server';

export function middleware(req: NextRequest) {
  if (req.nextUrl.pathname.startsWith('/admin')) {
    const basicAuth = req.headers.get('authorization');
    const url = req.nextUrl;

    if (basicAuth) {
      const authValue = basicAuth.split(' ')[1];
      const [user, pwd] = atob(authValue).split(':');

      const expectedUser = process.env.ADMIN_USERNAME;
      const expectedPassword = process.env.ADMIN_PASSWORD;

      if (user === expectedUser && pwd === expectedPassword) {
        return NextResponse.next();
      }
    }

    url.pathname = '/api/auth-required'; // Or directly return a 401 response
    
    // Return a 401 response to trigger the browser's Basic Auth prompt
    return new NextResponse('Authentication required', {
      status: 401,
      headers: {
        'WWW-Authenticate': 'Basic realm="Secure Area"',
      },
    });
  }

  return NextResponse.next();
}

export const config = {
  matcher: '/admin/:path*',
};
