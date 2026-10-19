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
