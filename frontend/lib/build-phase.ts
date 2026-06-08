/** true trong `next build` — tránh gọi API nặng khi prerender sitemap/layout. */
export function isNextProductionBuild(): boolean {
  return process.env.NEXT_PHASE === "phase-production-build";
}
