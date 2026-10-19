/* Browser motion kernel: exact circle intersections, no interpolated rigid links.
 * Python remains the source of configuration, analytic boundaries and diagnostics.
 * Kept independent of the DOM so its results can be checked against Python.
 */
(function (root) {
  'use strict';
  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
  const mul = (a, s) => [a[0] * s, a[1] * s];
  const norm = a => Math.hypot(...a);
  const dot = (a, b) => a[0]*b[0] + a[1]*b[1];
  const perp = a => [-a[1], a[0]];
  const rotate = (a, t) => [a[0]*Math.cos(t)-a[1]*Math.sin(t), a[0]*Math.sin(t)+a[1]*Math.cos(t)];
  const wrap = t => Math.atan2(Math.sin(t), Math.cos(t));
  const arm = b => mul([Math.cos(b.arm_angle), Math.sin(b.arm_angle)], b.arm_length);
  function solve(p, theta, reference = 0) {
    const al = [-p.pivot_spacing/2, 0], ar = [p.pivot_spacing/2, 0];
    const bl = add(al, rotate(arm(p.left), theta));
    const delta = sub(bl, ar), h = norm(delta), r = p.right.arm_length, t = p.tie_length;
    const tol = Math.max(p.pivot_spacing, t, r, p.left.arm_length)*1e-10;
    if (!Number.isFinite(theta) || Math.min(r, t, p.left.arm_length, p.pivot_spacing) <= tol)
      return {status: 'degenerate'};
    if (h <= tol) return {status: Math.abs(r-t) <= tol ? 'coincident' : 'concentric'};
    const margin = Math.min(r+t-h, h-Math.abs(r-t));
    if (margin < -tol) return {status: 'impossible'};
    const tangent = Math.abs(margin) <= tol;
    const a = (h*h+(r-t)*(r+t))/(2*h), e = mul(delta, 1/h);
    const q = tangent ? 0 : Math.sqrt(Math.max(0, (r+t+h)*(r+t-h)*(h+r-t)*(h-r+t)/(4*h*h)));
    const br = add(add(ar, mul(e, a)), mul(perp(e), p.branch*q));
    const tr = reference + wrap(Math.atan2(br[1]-ar[1], br[0]-ar[0])-p.right.arm_angle-reference);
    const rod = sub(br, bl), vl = perp(sub(bl, al)), vr = perp(sub(br, ar));
    const numerator = dot(rod, vl), denominator = dot(rod, vr);
    const inputSine = Math.abs(numerator)/(t*p.left.arm_length), outputSine = Math.abs(denominator)/(t*r);
    const nearInput = inputSine <= Math.max(p.targets.warning_sine, 1e-9);
    const nearOutput = tangent || outputSine <= Math.max(p.targets.warning_sine, 1e-9);
    return {status: tangent ? 'tangent' : 'valid', theta_left: theta, theta_right: tr,
      a_left: al, a_right: ar, b_left: bl, b_right: br,
      c_left: add(al, rotate([p.left.axle_x, p.left.axle_y], theta)),
      c_right: add(ar, rotate([p.right.axle_x, p.right.axle_y], tr)),
      heading_left: theta+p.left.heading_offset, heading_right: tr+p.right.heading_offset,
      point: add(bl, mul(rod, p.actuation_fraction)), closure_error: Math.abs(norm(rod)-t),
      ratio: nearOutput ? null : numerator/denominator, nearInput, nearOutput, radial_margin: margin};
  }
  function crossesBoundary(from, to, boundaries) {
    if (Math.abs(from-to) <= 1e-12) return false;
    const lo = Math.min(from, to), hi = Math.max(from, to);
    return boundaries.some(t => t >= lo-1e-12 && t <= hi+1e-12);
  }
  const api = {solve, crossesBoundary, add, sub, mul, norm, rotate, wrap};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SteeringKinematics = api;
})(globalThis);
