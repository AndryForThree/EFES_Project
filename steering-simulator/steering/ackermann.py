"""Presentation-only Ackermann diagnosis; never changes search metrics or Pareto.

Fit a single nonnegative track/wheelbase ratio by minimizing the maximum
inner-wheel angular error over the complete, uniformly sampled mean-steering
interval. Positive steering suffices for the symmetric mechanisms we support.
"""
from dataclasses import dataclass
import math
import numpy as np
from .quadrilateral_search import ackermann_curve


@dataclass(frozen=True)
class AckermannFit:
    reference_wheelbase: float
    equivalent_wheelbase: float | None  # None: infinite limit, or unsupported; see status
    track: float
    reference_error: float
    fitted_error: float | None
    ratio: float | None  # track / equivalent wheelbase; zero explicitly means infinity
    status: str
    behavior: str


def ideal_inner(outer,ratio):
    outer=np.asarray(outer,dtype=float)
    return np.arctan2(np.sin(outer),np.cos(outer)-ratio*np.sin(outer))


def fit_ackermann(outer,inner,track,reference_wheelbase):
    outer=np.asarray(outer,dtype=float);inner=np.asarray(inner,dtype=float)
    if (outer.ndim!=1 or outer.shape!=inner.shape or len(outer)<2 or
        not np.all(np.isfinite(outer)) or not np.all(np.isfinite(inner)) or
        not math.isfinite(track) or track<=0 or not math.isfinite(reference_wheelbase) or reference_wheelbase<=0):
        raise ValueError('Dati Ackermann non validi: angoli finiti, carreggiata e passo positivi.')
    reference_error=float(np.max(np.abs(inner-ideal_inner(outer,track/reference_wheelbase))))
    active=(np.abs(outer)+np.abs(inner)>1e-12)
    a,b=outer[active],inner[active]
    if not len(a) or np.any((a<=0)|(b<=0)|(a>=math.pi)|(b>=math.pi)):
        return AckermannFit(reference_wheelbase,None,track,reference_error,None,None,'unsupported','Non rappresentabile')
    difference=b-a
    tolerance=1e-10
    positive=np.any(difference>tolerance);negative=np.any(difference < -tolerance)
    behavior=('Misto' if positive and negative else 'Ackermann' if positive else
              'Anti-Ackermann' if negative else 'Ruote parallele')
    def balance(ratio):
        error=inner-ideal_inner(outer,ratio)
        return float(error.max()+error.min())
    if balance(0.)<=0. or np.max(np.abs(difference))<=tolerance:
        ratio=0.
    else:
        # Each sample is matched exactly at cot(outer)-cot(inner). At their
        # maximum every residual is <= 0, providing a data-derived upper bound.
        matches=np.sin(b-a)/(np.sin(a)*np.sin(b))
        low=0.;high=float(max(1.,matches.max()))
        for _ in range(80):
            middle=(low+high)/2
            if balance(middle)>0:low=middle
            else:high=middle
        ratio=(low+high)/2
    fitted_error=float(np.max(np.abs(inner-ideal_inner(outer,ratio))))
    if ratio==0.:
        return AckermannFit(reference_wheelbase,None,track,reference_error,fitted_error,0.,'infinite',behavior)
    return AckermannFit(reference_wheelbase,track/ratio,track,reference_error,fitted_error,ratio,'finite',behavior)


def diagnose_ackermann(p,reference_wheelbase,target,count=241):
    curve=ackermann_curve(p,reference_wheelbase,target,count)
    track=p.pivot_spacing+p.right.axle_x-p.left.axle_x
    fit=fit_ackermann(curve['outer'],curve['inner'],track,reference_wheelbase)
    equivalent=ideal_inner(curve['outer'],fit.ratio) if fit.ratio is not None else None
    return fit,curve,equivalent
