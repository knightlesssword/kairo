import type { NextConfig } from "next";

// covers render via plain <img> (see components/chat/anime-card.tsx), so no
// images.remotePatterns block is needed. if covers ever move to next/image,
// re-add: images: { remotePatterns: [{ protocol: "https", hostname: "s4.anilist.co" }] }.
const nextConfig: NextConfig = {};

export default nextConfig;
