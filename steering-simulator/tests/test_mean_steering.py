"""Mean steering must preserve exact closure and mirror left/right motion."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import shutil
import subprocess
import numpy as np
import pytest
from steering.parameters import Parameters, symmetric_steering
from steering.kinematics import steering_input, steering_limit, solve, select_pose


@pytest.mark.skipif(not shutil.which('node'), reason='Browser parity needs Node')
def test_mean_command_mirrors_wheels_and_clamps_both_sides():
    cases = []
    for beta in (-60, -30, 0, 30, 60):
        p = symmetric_steering(Parameters(), 25, 180, math.radians(beta))
        limit, geometric = steering_limit(p)
        for fraction in (0, .3, .8, 1, 2):
            m = limit*fraction
            cases.append({'p':asdict(p),'limit':limit,'geometric':geometric,'m':m})
            applied = min(m, limit)
            left = steering_input(p, applied)
            pose = select_pose(solve(p, left), p.branch)
            assert pose is not None
            assert (pose.theta_left+pose.theta_right)/2 == pytest.approx(applied, abs=1e-9)
    kernel = Path(__file__).parents[1]/'visualization/browser/kinematics.js'
    script = '''const k=require(process.argv[1]);
    const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));
    process.stdout.write(JSON.stringify(cases.map(c=>({
      positive:k.resolveSteering(c.p,c.m,c.limit,c.geometric),
      negative:k.resolveSteering(c.p,-c.m,c.limit,c.geometric)}))));'''
    result = json.loads(subprocess.run(['node','-e',script,str(kernel)],input=json.dumps(cases),
                                      text=True,capture_output=True,check=True).stdout)
    for c, pair in zip(cases, result):
        a, b = pair['positive'], pair['negative']
        assert a['limited'] == b['limited']
        assert a['angle'] == -b['angle']
        assert a['pose'] is not None and b['pose'] is not None
        np.testing.assert_allclose([a['pose']['theta_left'],a['pose']['theta_right']],
                                   [-b['pose']['theta_right'],-b['pose']['theta_left']],atol=1e-8)
        for outcome in (a,b):
            pose = outcome['pose']
            assert (pose['heading_left']+pose['heading_right'])/2 == pytest.approx(outcome['angle'],abs=1e-9)
            assert pose['closure_error'] < c['p']['tie_length']*1e-9
