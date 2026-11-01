import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  // The theme toggle has the bottom-left corner; the dev-only indicator moves out of its way.
  devIndicators: { position: "bottom-right" },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
