import type { NextConfig } from 'next'

const apiProxyUrl = (process.env.API_PROXY_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiProxyUrl}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
