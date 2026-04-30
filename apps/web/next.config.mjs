/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: {
    unoptimized: true
  },
  transpilePackages: ["@crosswalks/contracts", "@crosswalks/ui"]
};

export default nextConfig;
