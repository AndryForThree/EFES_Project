"""Small parity check for the new browser path; no browser/package dependency."""
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest
from steering.kinematics import neutral_tie_length, select_pose, solve
from steering.parameters import Parameters, Bracket

NODE = shutil.which('node')
KERNEL = Path(__file__).parents[1] / 'visualization/browser/kinematics.js'


@pytest.mark.skipif(not NODE, reason='Node is only needed to check the browser kernel')
def test_browser_matches_python_and_stops_at_boundaries():
    asymmetric = Parameters(left=Bracket(arm_length=30, arm_angle=1.4),
                            right=Bracket(arm_length=40, arm_angle=1.7, axle_x=32, axle_y=8), symmetric=False)
    asymmetric = replace(asymmetric, tie_length=neutral_tie_length(asymmetric))
    cases = [(replace(p, branch=branch), angle) for p in (Parameters(), asymmetric)
             for branch in (-1, 1) for angle in (-.4, 0, .4, math.pi/2)]
    cases += [(replace(Parameters(), tie_length=10), 0)]
    script = '''const k=require(process.argv[1]);
    const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));
    const results=cases.map(c=>k.solve(c.p,c.angle));
    process.stdout.write(JSON.stringify({results,blocked:k.crossesBoundary(1.4,1.8,[Math.PI/2]),
      allowed:k.crossesBoundary(.1,.2,[Math.PI/2])}));'''
    response = json.loads(subprocess.run([NODE, '-e', script, str(KERNEL)],
                          input=json.dumps([{'p': asdict(p), 'angle': angle} for p, angle in cases]),
                          text=True, check=True, capture_output=True).stdout)
    assert response['blocked'] and not response['allowed']
    for (p, angle), actual in zip(cases, response['results']):
        solution = solve(p, angle)
        assert actual['status'] == solution.status
        expected = select_pose(solution, p.branch)
        if expected is None:
            assert 'b_right' not in actual
            continue
        for name in ('b_left', 'b_right', 'c_left', 'c_right', 'point', 'theta_left', 'theta_right'):
            np.testing.assert_allclose(actual[name], getattr(expected, name), atol=1e-9)
        assert actual['closure_error'] < p.length_tolerance


@pytest.mark.skipif(not NODE, reason='Node is only needed to check the browser kernel')
def test_limit_is_independent_of_frame_steps_and_history():
    from steering.kinematics import toggle_angles
    from steering.parameters import symmetric_steering
    configurations = [symmetric_steering(Parameters(), 25, 180, math.radians(beta))
                      for beta in (-30, 30)]
    # An exceptional limit with coincident circles must not retain an old pose.
    configurations.append(symmetric_steering(Parameters(), 180, 180, 0))
    payload = [{'p': asdict(p), 'boundaries': toggle_angles(p, -p.display_range, p.display_range)}
               for p in configurations]
    script = '''const k=require(process.argv[1]);
    const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));
    const results=cases.map(({p,boundaries})=>{
      const limits=k.motionLimits(p,boundaries);
      const sign=limits.upperGeometric?1:-1;
      const target=sign*p.display_range;
      const final=k.resolveMotion(p,target,limits);
      for(const step of [.001,.037,.2]){
        for(let a=0;Math.abs(a)<Math.abs(target);a+=sign*step) k.resolveMotion(p,a,limits);
        const actual=k.resolveMotion(p,target,limits);
        if(JSON.stringify(actual)!==JSON.stringify(final))throw Error('History-dependent limit');
      }
      const retreat=k.resolveMotion(p,0,limits);
      return {final,retreat,limits};
    });process.stdout.write(JSON.stringify(results));'''
    # Use a wide display range to include the coincident endpoint at -90°.
    payload[-1]['p']['display_range'] = math.pi
    payload[-1]['boundaries'] = toggle_angles(configurations[-1], -math.pi, math.pi)
    # Choose the coincident negative endpoint explicitly in this last case.
    script = script.replace('const sign=limits.upperGeometric?1:-1;',
                            "const sign=p.left.arm_length===180?-1:(limits.upperGeometric?1:-1);")
    result = json.loads(subprocess.run([NODE, '-e', script, str(KERNEL)], input=json.dumps(payload),
                                      text=True, check=True, capture_output=True).stdout)
    for item in result:
        assert item['final']['limited']
        assert item['retreat']['angle'] == 0
        assert item['retreat']['pose']['theta_right'] == pytest.approx(0, abs=1e-12)
    assert result[-1]['final']['pose'] is None
    assert result[-1]['final']['status'] == 'coincident'
    for item in result[:-1]:
        assert item['final']['pose']['status'] == 'tangent'
        assert item['final']['pose']['theta_left'] == item['final']['angle']
