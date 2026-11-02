
import type {NextConfig} from 'next';

const nextConfig: NextConfig = {
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'picsum.photos',
        port: '',
        pathname: '/**',
      },
    ],
  },
  // Expose environment variable to the browser
  env: {
    NEXT_PUBLIC_BACKEND_BASE_URL: process.env.BACKEND_BASE_URL,
    NEXT_PUBLIC_DISABLE_AUTH: process.env.NEXT_PUBLIC_DISABLE_AUTH || 'false', // Corrected: Use NEXT_PUBLIC_ prefix
  },
};

export default nextConfig;

    