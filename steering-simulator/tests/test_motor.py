"""Actuator closure, local sensitivity, invalid inputs and browser parity."""
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import shutil
import subprocess
import numpy as np
import pytest
from steering.motor import at_steering, build_range, solve_motor
from steering.parameters import Parameters, symmetric_steering


@pytest.mark.parametrize('assembly', [1,-1])
@pytest.mark.parametrize('inclination', [0,15,-15])
def test_motor_closure_and_sensitivity(assembly,inclination):
    p=symmetric_steering(Parameters(),25,180,math.radians(inclination))
    p=replace(p,motor=replace(p.motor,assembly=assembly))
    interval=build_range(p)
    assert interval.valid,interval.reason
    for phi in np.linspace(interval.phi_lower*.9,interval.phi_upper*.9,9):
        state=solve_motor(p,interval,float(phi))
        assert state is not None
        assert state.closure_error<1e-7
        assert state.pose.closure_error<p.length_tolerance
        assert state.phi-interval.neutral_phi==pytest.approx(phi,abs=1e-9)
        assert (state.pose.heading_left+state.pose.heading_right)/2==pytest.approx(state.steering,abs=1e-10)
        if state.sensitivity is not None:
            step=1e-5
            before=solve_motor(p,interval,float(phi-step))
            after=solve_motor(p,interval,float(phi+step))
            assert state.sensitivity==pytest.approx((after.steering-before.steering)/(2*step),rel=1e-4,abs=1e-6)
    # Large requests always resolve to fixed, repeatable sector endpoints.
    for target in (-10,10):
        a=solve_motor(p,interval,target)
        b=solve_motor(p,interval,target)
        assert a.steering==b.steering
        assert a.phi==b.phi


def test_invalid_neutral_and_singular_neutral():
    p=Parameters()
    assert not build_range(replace(p,motor=replace(p.motor,connecting_length=1))).valid
    # M and T aligned, circles externally tangent at neutral.
    assert not build_range(replace(p,motor=replace(p.motor,connecting_length=45))).valid


@pytest.mark.skipif(not shutil.which('node'),reason='Browser parity needs Node')
def test_motor_browser_matches_python():
    p=Parameters();interval=build_range(p)
    angles=[interval.phi_lower,-.5,0,.5,interval.phi_upper]
    script="""const k=require(process.argv[1]),args=JSON.parse(require('fs').readFileSync(0,'utf8'));
    process.stdout.write(JSON.stringify(args.angles.map(phi=>k.resolveMotor(args.p,phi,args.range))));"""
    kernel=Path(__file__).parents[1]/'visualization/browser/kinematics.js'
    results=json.loads(subprocess.run(['node','-e',script,str(kernel)],
        input=json.dumps({'p':asdict(p),'range':asdict(interval),'angles':angles}),
        text=True,capture_output=True,check=True).stdout)
    for phi,actual in zip(angles,results):
        expected=solve_motor(p,interval,phi)
        assert actual['actuator']['steering']==pytest.approx(expected.steering,abs=1e-8)
        np.testing.assert_allclose(actual['actuator']['pin'],expected.pin,atol=1e-7)
        assert actual['actuator']['closure_error']<1e-7
