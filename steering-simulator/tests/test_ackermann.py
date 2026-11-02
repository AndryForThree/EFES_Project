"""Small analytical checks of the diagnostic fit, separate from optimization."""
import math
import numpy as np
import pytest
from steering.ackermann import diagnose_ackermann,fit_ackermann,ideal_inner
from steering.parameters import modular_defaults,steering_from_lengths


def test_equivalent_wheelbase_recovers_known_ideal_and_handles_parallel_reverse():
    outer=np.linspace(0.,.4,101);track=230.;wheelbase=420.
    inner=ideal_inner(outer,track/wheelbase)
    fit=fit_ackermann(outer,inner,track,200.)
    assert fit.status=='finite' and fit.behavior=='Ackermann'
    assert fit.equivalent_wheelbase==pytest.approx(wheelbase,rel=1e-10)
    assert fit.fitted_error<1e-12 and fit.reference_error>fit.fitted_error
    parallel=fit_ackermann(outer,outer,track,200.)
    assert parallel.status=='infinite' and parallel.behavior=='Ruote parallele'
    assert parallel.equivalent_wheelbase is None and parallel.ratio==0 and parallel.fitted_error<1e-12
    reverse=fit_ackermann(outer,.8*outer,track,200.)
    assert reverse.status=='infinite' and reverse.behavior=='Anti-Ackermann'
    assert reverse.fitted_error>0 and reverse.equivalent_wheelbase is None
    invalid=fit_ackermann(outer,-outer,track,200.)
    assert invalid.status=='unsupported' and invalid.ratio is None
    with pytest.raises(ValueError):fit_ackermann(outer,inner,0.,200.)


def test_single_fitted_wheelbase_reduces_worst_error_over_entire_geometry_curve():
    p=steering_from_lengths(modular_defaults(),180.,30.,170.)
    fit,curve,equivalent=diagnose_ackermann(p,200.,.3)
    assert fit.status=='finite' and len(equivalent)==241
    assert fit.fitted_error==pytest.approx(np.abs(curve['inner']-equivalent).max())
    assert fit.fitted_error<=fit.reference_error+1e-12
    for ratio in (fit.ratio*.9,fit.ratio*1.1):
        error=np.abs(curve['inner']-ideal_inner(curve['outer'],ratio)).max()
        assert error>=fit.fitted_error-1e-12
    # One fixed reference fits all samples; it does not fit each angle separately.
    assert fit.fitted_error>1e-6
    assert math.isfinite(fit.equivalent_wheelbase)
