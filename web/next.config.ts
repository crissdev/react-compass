import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: false,
  reactStrictMode: true,
};

export default nextConfig;
