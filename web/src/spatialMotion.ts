export type SpatialMotion = {
  origin: { x: number; y: number; z: number };
  elapsed: number;
  period: number;
};

// Same trajectory as the server; interpolate locally without control requests.
export function automaticPosition(motion: SpatialMotion, elapsed: number) {
  const t = Math.max(0, elapsed);
  const phase = Math.atan2(motion.origin.x, motion.origin.y);
  const angle = phase + (t * Math.PI * 2) / motion.period;
  const u = Math.min(1, t / 1.5),
    blend = u * u * (3 - 2 * u);
  return {
    x: motion.origin.x + (1.5 * Math.sin(angle) - motion.origin.x) * blend,
    y: motion.origin.y + (1.5 * Math.cos(angle) - motion.origin.y) * blend,
    z: motion.origin.z + (0.35 * Math.sin(angle / 2) - motion.origin.z) * blend,
  };
}
