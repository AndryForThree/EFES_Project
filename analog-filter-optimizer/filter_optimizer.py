#!/usr/bin/env python3
"""Compare analog Butterworth filters for an ideal sampled white spectrum."""

import argparse
from functools import lru_cache
import math
import sys
import warnings

import numpy as np
from scipy import integrate, optimize, signal


def _positive(name, value):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")


def _integer(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _band(fb, fs):
    _positive("fb", fb)
    _positive("fs", fs)
    if fb >= fs / 2:
        raise ValueError("useful bandwidth must satisfy 0 < fb < fs/2")


@lru_cache(maxsize=32)
def _sections(order):
    # Unit rad/s cutoff; evaluating at f/Fc gives the desired response in Hz.
    # Second-order sections avoid large high-order polynomial coefficients.
    return signal.butter(order, 1.0, analog=True, output="sos")


def butterworth_magnitude(frequency, order, fc):
    _integer("order", order)
    _positive("fc", fc)
    frequency = np.asarray(frequency, dtype=float)
    if not np.all(np.isfinite(frequency)):
        raise ValueError("frequencies must be finite")
    magnitude = np.ones(frequency.size)
    for section in _sections(order):
        _, response = signal.freqs(section[:3], section[3:], worN=np.abs(frequency.ravel()) / fc)
        magnitude *= np.abs(response)
    if not np.all(np.isfinite(magnitude)):
        raise ValueError("frequency response exceeded the numerical range")
    return magnitude.reshape(frequency.shape)


def passband_distortion(order, fc, fb):
    _positive("fb", fb)
    return max(0.0, 1.0 - float(butterworth_magnitude(fb, order, fc)))


def aliasing_power_ratio(order, fc, fb, fs, max_replicas=1, *, integration_bandwidth=None):
    """Return alias power in ±integration_bandwidth / (2*Fb*S0).

    The integration bandwidth defaults to Fb and may extend to Fs/2.
    Both measurements retain the original useful-band power as reference.
    """
    _integer("order", order)
    _positive("fc", fc)
    _band(fb, fs)
    _integer("max_replicas", max_replicas)
    bandwidth = fb if integration_bandwidth is None else integration_bandwidth
    _positive("integration_bandwidth", bandwidth)
    if bandwidth > fs / 2:
        raise ValueError("integration_bandwidth must not exceed fs/2")

    # Even |H| gives Pa/Ps = (B/Fb) integral[-1,1]
    # sum[k=1..K] |H(k Fs + t B)|² dt, with B the integration bandwidth.
    # Both signs of k are included. Ps always remains 2*Fb*S0, even for B=Fs/2.
    # This is a finite-replica approximation, not an infinite-sum estimate.
    # Fixed integration precision is separate from the selected replica count.
    ratio = 0.0
    for start in range(1, max_replicas + 1, 1024):
        replicas = np.arange(start, min(start + 1024, max_replicas + 1), dtype=float)

        def integrand(t):
            magnitudes = butterworth_magnitude(replicas * fs + t * bandwidth, order, fc)
            return float(np.dot(magnitudes, magnitudes))

        contribution, _ = integrate.quad(
            integrand, -1.0, 1.0, epsabs=0.0, epsrel=1e-8, limit=200,
        )
        ratio += contribution
    return ratio * (bandwidth / fb)


def quantization_snr(bits, vref, signal_amplitude, fb, fs):
    """Ideal sine-wave quantization estimate: (Nyquist SNR, useful-band SNR)."""
    _integer("bits", bits)
    _positive("VREF", vref)
    _positive("SIGNAL_AMPLITUDE", signal_amplitude)
    if signal_amplitude > vref / 2:
        raise ValueError("SIGNAL_AMPLITUDE must not exceed VREF/2 for an unclipped sine wave")
    _band(fb, fs)
    # VREF is the ADC's full input span. Amplitude is sine peak relative to
    # its mean, in volts (not RMS or peak-to-peak). BITS is ADC resolution,
    # independent of the analog filter order.
    nyquist = 6.02 * bits + 1.76 + 20 * math.log10(2 * signal_amplitude / vref)
    band = nyquist + 10 * (math.log10(fs) - math.log10(2 * fb))
    return nyquist, band


def total_design_error(fc, order, fb, fs, max_replicas=1):
    # Equal-weight engineering index, not a rigorous acquired-signal error bound.
    return passband_distortion(order, fc, fb) + math.sqrt(
        aliasing_power_ratio(order, fc, fb, fs, max_replicas)
    )


def optimize_cutoff(order, fb, fs, fc_min=None, fc_max=None,
                    max_replicas=1):
    _band(fb, fs)
    fc_min = fb / 2 if fc_min is None else fc_min
    fc_max = fs if fc_max is None else fc_max
    _positive("fc_min", fc_min)
    _positive("fc_max", fc_max)
    if fc_min >= fc_max:
        raise ValueError("fc_min must be smaller than fc_max")
    lower, upper = math.log(fc_min), math.log(fc_max)

    # A coarse scan brackets the best basin; bounded minimization alone can
    # miss an interior minimum when the objective flattens near an endpoint.
    def objective(log_fc):
        return total_design_error(math.exp(log_fc), order, fb, fs,
                                  max_replicas)

    with warnings.catch_warnings(record=True) as numerical_warnings:
        warnings.simplefilter("always", RuntimeWarning)
        grid = np.linspace(lower, upper, 33)
        values = [objective(x) for x in grid]
        candidates = [(value, x) for value, x in zip(values, grid)]
        brackets = [(grid[0], grid[1]), (grid[-2], grid[-1])]
        for i in range(1, len(grid) - 1):
            if values[i] < values[i - 1] and values[i] <= values[i + 1]:
                brackets.append((grid[i - 1], grid[i + 1]))
        for bracket in brackets:
            result = optimize.minimize_scalar(
                objective, bounds=bracket,
                method="bounded", options={"xatol": 1e-8},
            )
            if not result.success:
                raise RuntimeError(f"cutoff optimization failed: {result.message}")
            candidates.append((result.fun, result.x))
        _, optimum = min(candidates)
    if numerical_warnings:
        warnings.warn(
            f"N={order}: numerical warnings occurred during the cutoff search; "
            f"the optimum may be unreliable. First warning: {numerical_warnings[0].message}",
            RuntimeWarning, stacklevel=2,
        )
    if min(optimum - lower, upper - optimum) <= 1e-5 * max(1, upper - lower):
        warnings.warn(f"N={order}: optimum at a search boundary; inspect the cutoff search interval",
                      RuntimeWarning, stacklevel=2)
    fc = math.exp(optimum)
    distortion = passband_distortion(order, fc, fb)
    aliasing = math.sqrt(aliasing_power_ratio(order, fc, fb, fs, max_replicas))
    aliasing_nyquist = math.sqrt(aliasing_power_ratio(
        order, fc, fb, fs, max_replicas, integration_bandwidth=fs / 2,
    ))
    return {"order": order, "fc": fc, "distortion": distortion, "aliasing": aliasing,
            "snra": -20 * math.log10(aliasing) if aliasing > 0 else math.inf,
            "aliasing_nyquist": aliasing_nyquist,
            "snra_nyquist": -20 * math.log10(aliasing_nyquist) if aliasing_nyquist > 0 else math.inf,
            "total": distortion + aliasing}


# Computational guard only: reaching it is a failure, never a design result.
MAX_NUMERICAL_ORDER = 64
TARGET_MARGIN_DB = 20.0


def optimize_orders(fb, fs, snrq, max_replicas=1):
    """Yield optima in [Fb/2, Fs] until SNRa - SNRq reaches 20 dB."""
    if not math.isfinite(snrq):
        raise ValueError("quantization SNR must be finite")
    for order in range(1, MAX_NUMERICAL_ORDER + 1):
        with warnings.catch_warnings(record=True) as numerical_warnings:
            warnings.simplefilter("always")
            row = optimize_cutoff(order, fb, fs, fb / 2, fs,
                                  max_replicas)
        for warning in numerical_warnings:
            warnings.warn(str(warning.message), warning.category, stacklevel=2)
        if not math.isfinite(row["snra"]):
            raise RuntimeError(f"N={order}: aliasing is outside numerical precision; "
                               "the 20 dB target cannot be verified")
        row["margin"] = row["snra"] - snrq
        yield row
        if row["margin"] >= TARGET_MARGIN_DB:
            if numerical_warnings:
                raise RuntimeError("the 20 dB target cannot be confirmed because of "
                                   "numerical or search-boundary warnings; adjust "
                                   "--MAX_REPLICAS and check the bandwidth and sampling rate")
            return
    raise RuntimeError(f"20 dB target not reached before the numerical safety limit "
                       f"of order {MAX_NUMERICAL_ORDER}; no qualifying order found")


class _EqualsHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action):
        text = super()._format_action_invocation(action)
        if action.option_strings and action.nargs != 0:
            return text.replace(" ", "=", 1)
        return text

    def _format_actions_usage(self, actions, groups):
        text = super()._format_actions_usage(actions, groups)
        for action in actions:
            if action.option_strings and action.nargs != 0:
                option = action.option_strings[0]
                value = self._format_args(action, self._get_default_metavar_for_optional(action))
                text = text.replace(f"{option} {value}", f"{option}={value}")
        return text


def _parser():
    parser = argparse.ArgumentParser(
        formatter_class=_EqualsHelpFormatter,
        allow_abbrev=False,
        description=("Compare analog Butterworth anti-aliasing filters (unity DC gain). "
                     "Use --NAME=VALUE. Missing inputs are requested at startup. "
                     "Cutoff search limits are fixed at FB/2 and FS. "
                     "Report aliasing in FB and FS/2, both relative to useful-band power. "
                     "Orders increase from 1 until the useful-band margin reaches 20 dB."),
        epilog=("Model: flat two-sided analog PSD, ideal uniform sampling; phase ignored. "
                "No coherent PWM noise, jitter, ADC nonlinearities or acquisition errors. "
                "Higher orders do not model cascaded unbuffered passive RC stages. "
                "SNRq assumes a sine-wave signal, white uncorrelated quantization noise "
                "and ideal digital band limiting: 6.02*BITS + 1.76 + "
                "20*log10(2*SIGNAL_AMPLITUDE/VREF), plus the useful-band correction."),
    )
    parser.add_argument("--FB", dest="fb", type=float, help="useful bandwidth in Hz")
    parser.add_argument("--FS", dest="fs", type=float, help="sampling rate in Hz")
    parser.add_argument("--BITS", dest="bits", type=int, help="ADC bits")
    parser.add_argument("--VREF", dest="vref", type=float, help="ADC reference / full input span in volts (input range 0..VREF)")
    parser.add_argument("--SIGNAL_AMPLITUDE", dest="signal_amplitude", type=float,
                        help="useful sine-wave peak amplitude relative to its mean in volts (not RMS or peak-to-peak)")
    parser.add_argument("--MAX_REPLICAS", dest="max_replicas", type=int, default=1,
                        help="number of included replica pairs k=±1,...,±N (default: 1)")
    return parser


def main(argv=None):
    parser = _parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    for argument in arguments:
        if argument not in ("-h", "--help") and (not argument.startswith("--") or "=" not in argument):
            parser.error(f"use --NAME=VALUE with uppercase parameter names: {argument!r}")
    args = parser.parse_args(arguments)
    try:
        for name, label, conversion in (
            ("fb", "Useful bandwidth [Hz]", float),
            ("fs", "Sampling frequency [Hz]", float),
            ("bits", "ADC resolution [bits]", int),
            ("vref", "ADC reference / full input span [V]", float),
            ("signal_amplitude", "Useful sine-wave peak amplitude relative to its mean [V]", float),
        ):
            if getattr(args, name) is not None:
                continue
            option = "--" + name.upper()
            try:
                entered = input(f"{option} ({label}) = ").strip()
            except EOFError:
                raise ValueError(f"{option} is required: pass it on the command line "
                                 "or enter it at startup") from None
            if not entered:
                raise ValueError(f"{option} is required; an empty value is not allowed")
            try:
                setattr(args, name, conversion(entered))
            except ValueError:
                raise ValueError(f"{option}: invalid numeric value {entered!r}") from None
        _band(args.fb, args.fs)
        _integer("max_replicas", args.max_replicas)
        nyquist, band = quantization_snr(args.bits, args.vref, args.signal_amplitude, args.fb, args.fs)
        fc_min = args.fb / 2
        fc_max = args.fs
        print(f"Useful bandwidth: {args.fb:g} Hz\nSampling frequency: {args.fs:g} Hz")
        print(f"ADC resolution: {args.bits} bits\nADC VREF / full input span: {args.vref:g} V")
        print(f"Useful sine-wave peak amplitude relative to its mean: {args.signal_amplitude:g} V")
        print(f"Cutoff search: [{fc_min:g}, {fc_max:g}] Hz (fixed at FB/2 and FS)")
        print(f"Replica pairs included: {args.max_replicas} (k=±1,...,±{args.max_replicas}); finite-replica approximation.")
        print("SNRq_Nyquist = 6.02*BITS + 1.76 + 20*log10(2*SIGNAL_AMPLITUDE/VREF)")
        print("SNRq_Band = SNRq_Nyquist + 10*log10(FS/(2*FB))")
        print(f"Ideal quantization SNR: Nyquist band {nyquist:.3f} dB; useful band {band:.3f} dB")
        print("Automatic order search: start at N=1; stop at useful-band margin >= 20 dB for the included replicas.")
        print("Flat two-sided input PSD; aliasing referenced to unfiltered useful-band power.")
        print("Alias_FB integrates [-FB, FB]; Alias_FS/2 integrates [-FS/2, FS/2].")
        print("Both alias RMS percentages and SNRa values use Ps = 2*FB*S0; SNRa excludes quantization noise.")
        print("E_total = maximum amplitude distortion + useful-band RMS aliasing (engineering index).\n")
        print(" N  Fc_opt [Hz]  Dist_max [%]  Alias_FB [%]  Alias_FS/2 [%]  SNRa_FB [dB]  SNRa_FS/2 [dB]  SNRq_FB [dB]  Margin_FB [dB]  E_total [%]")
        for row in optimize_orders(args.fb, args.fs, band,
                                   args.max_replicas):
            print(f"{row['order']:2d}  {row['fc']:11.5g}  {100 * row['distortion']:12.6g}  "
                  f"{100 * row['aliasing']:12.6g}  {100 * row['aliasing_nyquist']:14.6g}  "
                  f"{row['snra']:12.3f}  {row['snra_nyquist']:14.3f}  {band:12.3f}  "
                  f"{row['margin']:14.3f}  {100 * row['total']:11.6g}")
        print(f"\nFirst order meeting the 20 dB target for the included replicas: N={row['order']} (margin {row['margin']:.3f} dB).")
        print("SNRq: ideal useful-band estimate. Positive margin: aliasing below quantization noise.")
        print("Filter order also increases circuit complexity; the index alone does not select a physical circuit.")
    except (ValueError, RuntimeError, EOFError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
