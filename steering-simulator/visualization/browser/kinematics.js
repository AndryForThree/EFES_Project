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
    const nearInput = inputSine <= Math.max(0.05, 1e-9);
    const nearOutput = tangent || outputSine <= Math.max(0.05, 1e-9);
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
  function motionLimits(p, boundaries) {
    // The connected assembly interval containing the straight neutral pose.
    // Determine it once from exact Python roots, never from animation frames.
    const negative = boundaries.filter(t => t < -1e-12);
    const positive = boundaries.filter(t => t > 1e-12);
    return {
      lower: Math.max(-p.display_range, ...negative),
      upper: Math.min(p.display_range, ...positive),
      lowerGeometric: negative.length > 0 && Math.max(...negative) >= -p.display_range,
      upperGeometric: positive.length > 0 && Math.min(...positive) <= p.display_range,
    };
  }
  function resolveMotion(p, requested, limits) {
    const angle = Math.max(limits.lower, Math.min(limits.upper, requested));
    const limited = (requested <= limits.lower && limits.lowerGeometric)
      || (requested >= limits.upper && limits.upperGeometric);
    // A fixed angle reference makes the displayed solution independent of history.
    const result = solve(p, angle, 0);
    return {angle, limited, pose: result.b_right ? result : null, status: result.status};
  }
  function resolveSteering(p, requested, limit, geometric) {
    const angle = Math.max(-limit, Math.min(limit, requested));
    const d=p.pivot_spacing, t=p.tie_length, length=p.left.arm_length;
    const discriminant=t*t-d*d*Math.sin(angle)**2;
    const u=-d*Math.cos(angle)+Math.sqrt(Math.max(0,discriminant));
    const sine=u/(2*length);
    if(discriminant < -(Math.max(d,t,length)**2)*1e-10 || Math.abs(sine)>1+1e-9)
      return {angle,limited:true,pose:null,status:'impossible'};
    const delta=Math.asin(Math.max(-1,Math.min(1,sine)))-(p.left.arm_angle-Math.PI/2);
    const result=solve(p,angle+delta,angle-delta);
    return {angle,limited:geometric && Math.abs(requested)>=limit-1e-12,
      pose:result.b_right ? result : null,status:result.status};
  }
  function motorAtSteering(p, mean, reference = 0) {
    const pose=resolveSteering(p,mean,Math.PI/2,false).pose;
    if(!pose)return null;
    const motor=p.motor, center=[motor.x,motor.y], delta=sub(pose.point,center);
    const h=norm(delta),r=motor.crank_radius,t=motor.connecting_length;
    const tol=Math.max(p.pivot_spacing,p.tie_length,p.left.arm_length,p.right.arm_length,r,t)*1e-10;
    if(h<=tol)return null;
    const margin=Math.min(r+t-h,h-Math.abs(r-t));
    if(margin < -tol)return null;
    const a=(h*h+(r-t)*(r+t))/(2*h),e=mul(delta,1/h);
    const q=Math.abs(margin)<=tol?0:Math.sqrt(Math.max(0,(r+t+h)*(r+t-h)*(h+r-t)*(h-r+t)/(4*h*h)));
    const pin=add(add(center,mul(e,a)),mul(perp(e),motor.assembly*q));
    const phi=reference+wrap(Math.atan2(pin[1]-center[1],pin[0]-center[0])-reference);
    const d=p.pivot_spacing,length=p.left.arm_length,beta=p.left.arm_angle-Math.PI/2;
    let deltaPrime=0,velocity=null;
    if(Math.abs(d-p.tie_length)<=Math.max(d,p.tie_length,length)*1e-10&&Math.abs(beta)<=1e-12)deltaPrime=0;
    else{
      const disc=p.tie_length**2-d*d*Math.sin(mean)**2;
      if(disc>Math.max(d,p.tie_length,length)**2*1e-10){
        const root=Math.sqrt(disc),u=-d*Math.cos(mean)+root,c=Math.sqrt(Math.max(0,1-(u/(2*length))**2));
        deltaPrime=c>1e-10?(d*Math.sin(mean)-d*d*Math.sin(mean)*Math.cos(mean)/root)/(2*length*c):NaN;
      }else deltaPrime=NaN;
    }
    if(Number.isFinite(deltaPrime))velocity=add(mul(perp(sub(pose.b_left,pose.a_left)),(1-p.actuation_fraction)*(1+deltaPrime)),mul(perp(sub(pose.b_right,pose.a_right)),p.actuation_fraction*(1-deltaPrime)));
    const rod=sub(pose.point,pin),numerator=dot(rod,perp(sub(pin,center))),denominator=velocity?dot(rod,velocity):NaN;
    const sensitivity=Number.isFinite(denominator)&&Math.abs(denominator)/(t*Math.max(p.left.arm_length,p.right.arm_length))>1e-8?numerator/denominator:null;
    return {pose,steering:mean,phi,pin,sensitivity,margin,closure_error:Math.abs(norm(rod)-t)};
  }
  function resolveMotor(p, requested, range) {
    if(!range.valid)return {pose:null,actuator:null,limited:true,angle:0,status:'motor_invalid'};
    const minPhi=Math.min(range.phi_at_lower,range.phi_at_upper),maxPhi=Math.max(range.phi_at_lower,range.phi_at_upper);
    const angle=Math.max(minPhi,Math.min(maxPhi,requested));
    let lo=range.mean_lower,hi=range.mean_upper;
    const increasing=range.phi_at_upper>range.phi_at_lower;
    let actuator;
    if(Math.abs(angle)<=1e-14)actuator=motorAtSteering(p,0,range.neutral_phi);
    else if(Math.abs(angle-range.phi_at_lower)<=1e-12)actuator=motorAtSteering(p,lo,range.neutral_phi);
    else if(Math.abs(angle-range.phi_at_upper)<=1e-12)actuator=motorAtSteering(p,hi,range.neutral_phi);
    else{
      for(let i=0;i<34;i++){
        const mid=(lo+hi)/2,state=motorAtSteering(p,mid,range.neutral_phi);
        if(!state)return {pose:null,actuator:null,limited:true,angle,status:'motor_invalid'};
        if((state.phi-range.neutral_phi<angle)===increasing)lo=mid;else hi=mid;
      }
      actuator=motorAtSteering(p,(lo+hi)/2,range.neutral_phi);
    }
    return {pose:actuator?.pose??null,actuator,angle,limited:requested<=minPhi+1e-12||requested>=maxPhi-1e-12,status:actuator?'valid':'motor_invalid'};
  }
  const api = {solve, crossesBoundary, motionLimits, resolveMotion, resolveSteering, motorAtSteering, resolveMotor, add, sub, mul, norm, rotate, wrap};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SteeringKinematics = api;
})(globalThis);
