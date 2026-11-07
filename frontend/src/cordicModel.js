// cordicModel.js
// JavaScript copy of the CORDIC block (backend/rtl_codegen/emit_cordic.py).
// It does the SAME integer steps as the Verilog, so the number you see on the
// canvas is exactly what the hardware gives.
//
//   x, y   : decimal value  -> integer x 256
//   angle  : decimal degrees -> integer x 100
//   result : converted back to decimals, gain already removed

export const COORD_SCALE = 256;
export const ANGLE_SCALE = 100;

const ITER        = 16;   // fixed number of rotation steps
const GUARD       = 4;    // extra bits for x and y
const ANGLE_BITS  = 6;    // extra bits for the angle
const K_INV       = 39797n;   // 0.60725 * 65536  (1 / CORDIC gain)

// atan(2^-i) in degrees x 100 x 64
const ATAN = Array.from({ length: ITER }, (_, i) =>
  BigInt(Math.round((Math.atan(2 ** -i) * 180 / Math.PI) * ANGLE_SCALE * (1 << ANGLE_BITS)))
);

// integer CORDIC (BigInt so the shifts behave like Verilog)
export function cordicInt(x, y, angle, dataWidth = 16) {
  let xs = BigInt(x), ys = BigInt(y), z = BigInt(angle);

  // step 1: bring the angle inside +-90 degrees
  if (z > 9000n)       { [xs, ys, z] = [-ys,  xs, z - 9000n]; }
  else if (z < -9000n) { [xs, ys, z] = [ ys, -xs, z + 9000n]; }
  z = z << BigInt(ANGLE_BITS);

  // step 2: guard bits
  let xt = xs << BigInt(GUARD);
  let yt = ys << BigInt(GUARD);

  // step 3: rotate
  for (let i = 0; i < ITER; i++) {
    const s = BigInt(i);
    if (z >= 0n) { [xt, yt, z] = [xt - (yt >> s), yt + (xt >> s), z - ATAN[i]]; }
    else         { [xt, yt, z] = [xt + (yt >> s), yt - (xt >> s), z + ATAN[i]]; }
  }

  // step 4: remove gain and guard bits (with rounding)
  const shift = BigInt(16 + GUARD);
  const round = 1n << (shift - 1n);
  const xo = (xt * K_INV + round) >> shift;
  const yo = (yt * K_INV + round) >> shift;

  // same wrap-around as the hardware output register
  return { x: Number(BigInt.asIntN(dataWidth, xo)), y: Number(BigInt.asIntN(dataWidth, yo)) };
}

// decimal in -> decimal out
export function cordicRotate(xDec, yDec, angleDeg, dataWidth = 16) {
  const xi = Math.round(xDec * COORD_SCALE);
  const yi = Math.round(yDec * COORD_SCALE);
  const ai = Math.round(angleDeg * ANGLE_SCALE);
  const out = cordicInt(xi, yi, ai, dataWidth);

  const maxCoord = 2 ** (dataWidth - 1) / COORD_SCALE;           // 128 for 16 bit
  const radius   = Math.hypot(xDec, yDec);
  let warning = "";
  if (Math.abs(angleDeg) > 180)  warning = "angle must be between -180 and 180";
  else if (radius >= maxCoord)   warning = `keep sqrt(x\u00B2+y\u00B2) below ${maxCoord}`;

  return { x: out.x / COORD_SCALE, y: out.y / COORD_SCALE, warning };
}
