export type SpatialMotion = {
  origin: { x: number; y: number; z: number };
  elapsed: number;
  period: number;
  kind?: "random";
  seed?: number;
};

// Same trajectory as the server; interpolate locally without control requests.
export function automaticPosition(motion: SpatialMotion, elapsed: number) {
  if (motion.kind === "random" && motion.seed !== undefined)
    return randomPosition(motion, elapsed, motion.seed);
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

function randomPosition(motion: SpatialMotion, elapsed: number, seed: number) {
  function random(index: number, lane: number) {
    let value =
      (seed ^
        Math.imul(index + 1, 0x9e3779b9) ^
        Math.imul(lane, 0x85ebca6b)) >>>
      0;
    value = Math.imul(value ^ (value >>> 16), 0x7feb352d) >>> 0;
    value = Math.imul(value ^ (value >>> 15), 0x846ca68b) >>> 0;
    return ((value ^ (value >>> 16)) >>> 0) / 4294967296;
  }
  const t = Math.max(0, elapsed),
    phase = random(0, 3) * Math.PI * 2;
  const clock = t / 6 + 0.22 * (Math.sin(t / 8 + phase) - Math.sin(phase));
  const index = Math.floor(clock),
    u = clock - index;
  function point(number: number) {
    if (number <= 0)
      return [
        Math.atan2(motion.origin.x, motion.origin.y),
        Math.hypot(motion.origin.x, motion.origin.y),
        motion.origin.z,
      ];
    const direction = random(number, 0);
    const angle =
      number === 1
        ? Math.atan2(motion.origin.x, motion.origin.y) +
          (direction >= 0.5 ? 1 : -1) * (0.8 + 2.2 * random(number, 4))
        : direction * Math.PI * 2;
    return [
      angle,
      0.9 + 1.8 * random(number, 1),
      -0.9 + 1.8 * random(number, 2),
    ];
  }
  const wrap = (angle: number) => Math.atan2(Math.sin(angle), Math.cos(angle));
  const [previous, current, following, after] = [
    index - 1,
    index,
    index + 1,
    index + 2,
  ].map(point);
  previous[0] = current[0] + wrap(previous[0] - current[0]);
  const followingAngle = following[0];
  following[0] = current[0] + wrap(followingAngle - current[0]);
  after[0] = following[0] + wrap(after[0] - followingAngle);
  const h00 = 2 * u ** 3 - 3 * u ** 2 + 1,
    h10 = u ** 3 - 2 * u ** 2 + u;
  const h01 = -2 * u ** 3 + 3 * u ** 2,
    h11 = u ** 3 - u ** 2;
  const polar = current.map((value, axis) => {
    const startVelocity =
      index === 0 ? 0 : (following[axis] - previous[axis]) * 0.3;
    const endVelocity = (after[axis] - current[axis]) * 0.3;
    return (
      h00 * value +
      h10 * startVelocity +
      h01 * following[axis] +
      h11 * endVelocity
    );
  });
  const [angle, r, height] = polar;
  const radius = Math.max(
    Math.min(0.7, Math.hypot(motion.origin.x, motion.origin.y)),
    r,
  );
  return {
    x: Math.max(-4, Math.min(4, radius * Math.sin(angle))),
    y: Math.max(-4, Math.min(4, radius * Math.cos(angle))),
    z: Math.max(-2, Math.min(2, height)),
  };
}
