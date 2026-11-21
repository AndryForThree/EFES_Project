import contextlib
import io
import math
import unittest
import warnings
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad

import filter_optimizer as filters


class FilterTests(unittest.TestCase):
    cli_inputs = [
        "--FB=100", "--FS=20000", "--BITS=12", "--VREF=3.3", "--SIGNAL_AMPLITUDE=1.65",
    ]

    def test_cutoff_and_dc_gain(self):
        for order in (1, 2, 4, 12):
            response = filters.butterworth_magnitude([0, 100], order, 100)
            self.assertAlmostEqual(response[0], 1.0)
            self.assertAlmostEqual(20 * math.log10(response[1]), -3.01029995664)

    def test_response_matches_butterworth_magnitude(self):
        frequencies = np.array([-900, -100, 0, 50, 100, 900])
        for order in (1, 2, 4, 12):
            expected = 1 / np.sqrt(1 + (frequencies / 100) ** (2 * order))
            np.testing.assert_allclose(
                filters.butterworth_magnitude(frequencies, order, 100), expected,
                rtol=1e-12, atol=1e-15,
            )

    def test_monotonic_errors_and_rejection(self):
        self.assertGreater(filters.passband_distortion(2, 200, 100),
                           filters.passband_distortion(2, 400, 100))
        self.assertLess(filters.aliasing_power_ratio(2, 200, 100, 20000),
                        filters.aliasing_power_ratio(2, 400, 100, 20000))
        self.assertGreater(filters.butterworth_magnitude(1000, 1, 100),
                           filters.butterworth_magnitude(1000, 4, 100))

    def test_first_order_against_infinite_replica_identity(self):
        # Independent closed-form periodic Lorentzian sum includes ALL replicas.
        fb, fs, fc = 100, 20000, 300
        a = fc / fs

        def alias_density(t):
            x = t * fb / fs
            all_replicas = (math.pi * a * math.sinh(2 * math.pi * a)
                            / (2 * (math.sinh(math.pi * a) ** 2
                                    + math.sin(math.pi * x) ** 2)))
            return all_replicas - 1 / (1 + (x / a) ** 2)

        reference = quad(alias_density, -1, 1, epsabs=1e-13)[0] / 2
        coarse = filters.aliasing_power_ratio(1, fc, fb, fs, max_replicas=1)
        fine = filters.aliasing_power_ratio(1, fc, fb, fs, max_replicas=10000)
        self.assertLess(coarse, fine)
        self.assertLessEqual(reference - fine, 1e-4 * fine)
        self.assertAlmostEqual(fine / reference, 1, delta=1e-4)

    def test_finite_replica_sum_matches_first_order_integrals(self):
        fb, fs, fc = 100, 20000, 300
        for count in (1, 3, 10, 1025):
            # Each positive/negative replica pair has this exact integral.
            reference = sum(fc / fb * (math.atan((k * fs + fb) / fc)
                                      - math.atan((k * fs - fb) / fc))
                            for k in range(1, count + 1))
            computed = filters.aliasing_power_ratio(1, fc, fb, fs, max_replicas=count)
            self.assertAlmostEqual(computed / reference, 1, delta=1e-8)
        self.assertEqual(filters.aliasing_power_ratio(1, fc, fb, fs),
                         filters.aliasing_power_ratio(1, fc, fb, fs, max_replicas=1))

    def test_default_optima_are_interior_and_reproducible(self):
        for order in range(1, 5):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                row = filters.optimize_cutoff(order, 100, 20000)
                expanded = filters.optimize_cutoff(order, 100, 20000, 0.1, 400000)
            self.assertGreater(row["fc"], 1)
            self.assertLess(row["fc"], 200000)
            self.assertAlmostEqual(expanded["fc"] / row["fc"], 1, delta=2e-4)
            self.assertAlmostEqual(row["snra"], -20 * math.log10(row["aliasing"]))
            for factor in (0.95, 1.05):
                nearby = filters.total_design_error(row["fc"] * factor, order, 100, 20000)
                self.assertLess(row["total"], nearby)

    def test_nyquist_aliasing_matches_exact_first_order_integral(self):
        fb, fs, fc = 100, 20000, 1000
        for count in (1, 3, 10):
            # The replica intervals tile [Fs/2, (K+1/2)*Fs] and its negative.
            expected = fc / fb * (math.atan((count + 0.5) * fs / fc)
                                  - math.atan(fs / (2 * fc)))
            actual = filters.aliasing_power_ratio(
                1, fc, fb, fs, count, integration_bandwidth=fs / 2,
            )
            self.assertAlmostEqual(actual, expected, places=12)

    def test_aliasing_bandwidth_keeps_useful_power_reference(self):
        fb, fs, fc, order, count = 100, 20000, 1000, 2, 3
        for bandwidth in (fb, 500, fs / 2):
            # Independent integration over signed frequencies and signed replicas.
            reference = sum(
                quad(lambda f: 1 / (1 + ((f + k * fs) / fc) ** (2 * order)),
                     -bandwidth, bandwidth, epsabs=1e-12)[0]
                for k in range(-count, count + 1) if k != 0
            ) / (2 * fb)
            actual = filters.aliasing_power_ratio(
                order, fc, fb, fs, count, integration_bandwidth=bandwidth,
            )
            self.assertAlmostEqual(actual, reference, places=12)

    def test_nyquist_metrics_and_unchanged_useful_band_objective(self):
        for order in range(1, 5):
            row = filters.optimize_cutoff(order, 100, 20000)
            self.assertGreater(row["aliasing_nyquist"], row["aliasing"])
            self.assertLess(row["snra_nyquist"], row["snra"])
            self.assertAlmostEqual(row["snra_nyquist"], -20 * math.log10(row["aliasing_nyquist"]))
            self.assertEqual(row["total"], row["distortion"] + row["aliasing"])

    def test_invalid_integration_bandwidth(self):
        for bandwidth in (0, -1, math.nan, math.inf, 10001):
            with self.subTest(bandwidth=bandwidth), self.assertRaises(ValueError):
                filters.aliasing_power_ratio(1, 1000, 100, 20000,
                                             integration_bandwidth=bandwidth)

    def test_boundary_warning(self):
        with self.assertWarnsRegex(RuntimeWarning, "search boundary"):
            row = filters.optimize_cutoff(2, 100, 20000, fc_min=10, fc_max=20)
        self.assertAlmostEqual(row["fc"], 20)

    def test_quantization_snr(self):
        self.assertEqual(filters.quantization_snr(12, 3.3, 1.65, 100, 20000), (74, 94))
        nyquist, band = filters.quantization_snr(12, 3.3, 0.825, 100, 20000)
        self.assertAlmostEqual(nyquist, 74 - 20 * math.log10(2))
        self.assertAlmostEqual(band - nyquist, 20)

    def test_quantization_formula_with_peak_amplitude(self):
        nyquist, band = filters.quantization_snr(10, 3.3, 0.2, 100, 20000)
        expected = 6.02 * 10 + 1.76 + 20 * math.log10(2 * 0.2 / 3.3)
        self.assertAlmostEqual(nyquist, expected)
        self.assertAlmostEqual(band, expected + 20)
        for vref, amplitude in ((0, 0.2), (-3.3, 0.2), (math.nan, 0.2),
                                (math.inf, 0.2), (3.3, 0), (3.3, -0.2),
                                (3.3, math.nan), (3.3, math.inf), (3.3, 1.66)):
            with self.subTest(vref=vref, amplitude=amplitude), self.assertRaises(ValueError):
                filters.quantization_snr(10, vref, amplitude, 100, 20000)

    def test_missing_reference_and_amplitude_are_requested(self):
        arguments = [arg for arg in self.cli_inputs
                     if not arg.startswith(("--VREF=", "--SIGNAL_AMPLITUDE="))]
        with patch("builtins.input", side_effect=["3.3", "1.65"]) as prompt:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(filters.main(arguments), 0)
        self.assertEqual(prompt.call_count, 2)
        self.assertIn("--VREF", prompt.call_args_list[0].args[0])
        self.assertIn("--SIGNAL_AMPLITUDE", prompt.call_args_list[1].args[0])
        self.assertIn("Nyquist band 74.000 dB; useful band 94.000 dB", output.getvalue())
        self.assertIn("20*log10(2*SIGNAL_AMPLITUDE/VREF)", output.getvalue())

    def test_invalid_inputs(self):
        for fb, fs in ((0, 20000), (-1, 20000), (10000, 20000),
                       (11000, 20000), (100, 0), (float("nan"), 20000)):
            with self.subTest(fb=fb, fs=fs), self.assertRaises(ValueError):
                filters.aliasing_power_ratio(1, 300, fb, fs)
        for argument in ("--BITS=0", "--VREF=nan", "--VREF=0", "--SIGNAL_AMPLITUDE=nan",
                         "--SIGNAL_AMPLITUDE=0", "--SIGNAL_AMPLITUDE=1.66", "--FB=10000",
                         "--MAX_REPLICAS=0"):
            with self.subTest(argument=argument):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    filters.main(self.cli_inputs + [argument])
                self.assertEqual(error.exception.code, 2)

    def test_uppercase_equals_syntax_and_help(self):
        args = filters._parser().parse_args(self.cli_inputs)
        self.assertEqual((args.fb, args.fs, args.bits), (100, 20000, 12))
        help_text = filters._parser().format_help()
        self.assertIn("--FB=FB", help_text)
        self.assertNotIn("--FB FB", help_text)
        self.assertNotIn("MAX_ORDER", help_text)
        self.assertNotIn("--FC_MAX", help_text)
        self.assertNotIn("--FC_MIN", help_text)
        self.assertNotIn("--TOLERANCE", help_text)
        self.assertNotIn("SIGNAL_RMS_RATIO", help_text)
        self.assertIn("--VREF=VREF", help_text)
        self.assertIn("--SIGNAL_AMPLITUDE=SIGNAL_AMPLITUDE", help_text)
        for arguments in (["--fb=100"], ["--FB", "100"], ["--MAX_ORDER=4"], ["--FC_MAX=2000"], ["--FC_MIN=1"], ["--F=100"]):
            with self.subTest(arguments=arguments):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    filters.main(arguments)

    def test_only_replica_count_has_an_input_default(self):
        args = filters._parser().parse_args([])
        self.assertEqual(args.max_replicas, 1)
        self.assertTrue(all(value is None for name, value in vars(args).items()
                            if name != "max_replicas"))

    def test_complete_cli_does_not_prompt(self):
        with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(filters.main(self.cli_inputs), 0)
        self.assertIn("N=4", output.getvalue())
        self.assertIn("[50, 20000] Hz (fixed at FB/2 and FS)", output.getvalue())
        self.assertIn("Alias_FB [%]", output.getvalue())
        self.assertIn("Alias_FS/2 [%]", output.getvalue())
        self.assertIn("SNRa_FS/2 [dB]", output.getvalue())
        self.assertIn("Ps = 2*FB*S0", output.getvalue())

    def test_cli_replica_count_override(self):
        with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(filters.main(self.cli_inputs + ["--MAX_REPLICAS=3"]), 0)
        self.assertIn("Replica pairs included: 3", output.getvalue())

    def test_missing_cli_values_are_requested(self):
        # Supply fb on the CLI and provide every remaining value at startup.
        with patch("builtins.input", side_effect=[item.split("=", 1)[1] for item in self.cli_inputs[1:]]) as prompt:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(filters.main(["--FB=100"]), 0)
        self.assertEqual(prompt.call_count, 4)
        self.assertNotIn("Useful bandwidth", prompt.call_args_list[0].args[0])
        self.assertIn("N=4", output.getvalue())

    def test_no_arguments_requests_all_values(self):
        with patch("builtins.input", side_effect=[item.split("=", 1)[1] for item in self.cli_inputs]) as prompt:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(filters.main([]), 0)
        self.assertEqual(prompt.call_count, 5)

    def test_missing_or_invalid_prompt_value_is_rejected(self):
        for answer in ("", "abc", EOFError()):
            effect = answer if isinstance(answer, Exception) else [answer]
            with self.subTest(answer=answer), patch("builtins.input", side_effect=effect):
                with contextlib.redirect_stderr(io.StringIO()) as output:
                    with self.assertRaises(SystemExit) as error:
                        filters.main([])
                self.assertEqual(error.exception.code, 2)
                self.assertIn("--FB", output.getvalue())

    def test_automatic_search_stops_at_first_qualifying_order(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            rows = list(filters.optimize_orders(100, 20000, 94, 1))
        self.assertEqual([row["order"] for row in rows], [1, 2, 3, 4])
        self.assertTrue(all(row["margin"] < 20 for row in rows[:-1]))
        self.assertGreaterEqual(rows[-1]["margin"], 20)

    def test_automatic_search_threshold_is_inclusive(self):
        with patch.object(filters, "optimize_cutoff", return_value={"snra": 114}) as optimizer:
            rows = list(filters.optimize_orders(100, 20000, 94, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["margin"], 20)
        optimizer.assert_called_once_with(1, 100, 20000, 50, 20000, 1)

    def test_unreachable_target_is_reported_as_failure(self):
        with patch.object(filters, "MAX_NUMERICAL_ORDER", 3):
            with patch.object(filters, "optimize_cutoff", return_value={"snra": 100}):
                with self.assertRaisesRegex(RuntimeError, "no qualifying order"):
                    list(filters.optimize_orders(100, 20000, 94, 1))

    def test_unreliable_aliasing_cannot_confirm_target(self):
        def unreliable(*args):
            warnings.warn("integration accuracy not achieved", RuntimeWarning)
            return {"snra": 120}

        with patch.object(filters, "optimize_cutoff", side_effect=unreliable):
            with self.assertWarns(RuntimeWarning), self.assertRaisesRegex(RuntimeError, "cannot be confirmed"):
                list(filters.optimize_orders(100, 20000, 94, 1))
        with patch.object(filters, "optimize_cutoff", return_value={"snra": math.inf}):
            with self.assertRaisesRegex(RuntimeError, "outside numerical precision"):
                list(filters.optimize_orders(100, 20000, 94, 1))


if __name__ == "__main__":
    unittest.main()
