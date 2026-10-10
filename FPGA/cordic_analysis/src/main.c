#include "cordic.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define PI      3.141592653589793238462643383279502884
#define TWO_PI  (2.0 * PI)

/*
 * ================================================================================
 * CORDIC SWEEP STRATEGY
 * ================================================================================
 *
 * The objective is to find CORDIC configurations capable of reaching a user
 * defined maximum angular error target.
 *
 * The CORDIC input width is fixed by the user, because it represents the
 * interface between the previous acquisition stage and the CORDIC.
 *
 *
 * 1. MINIMUM NUMBER OF ITERATIONS
 *
 * With N iterations, the last CORDIC micro-rotation is:
 *
 *      alpha(N-1) = atan(2^(-(N-1)))
 *
 * A configuration is considered interesting only if:
 *
 *      alpha(N-1) <= target_error
 *
 * This does NOT guarantee that the final CORDIC error satisfies the target.
 * It is only used to discard configurations whose last available angular
 * correction is already larger than the requested target.
 *
 *
 * 2. MINIMUM ANGLE FRACTIONAL BITS
 *
 * With Fz fractional bits:
 *
 *      LSB_angle = 2^(-Fz) rad
 *
 * Using rounding-to-nearest, the maximum output quantization error is:
 *
 *      0.5 * LSB_angle
 *
 * Therefore:
 *
 *      0.5 * 2^(-Fz) <= target_error
 *
 * Moreover, the angle representation should be fine enough to represent
 * the last CORDIC micro-rotation, therefore:
 *
 *      Fz >= N - 1
 *
 * Both conditions are used to determine the minimum Fz tested for each N.
 *
 *
 * 3. XY FRACTIONAL BITS
 *
 * No simple analytical minimum is imposed on xy_frac_bits.
 * They determine the internal precision of the X/Y datapath and are therefore
 * swept from 0 up to N+2 in order to observe when additional fractional bits
 * stop producing useful improvements.
 *
 *
 * 4. ERROR MEASUREMENT
 *
 * For every generated integer pair (X,Y), the SAME values are given to:
 *
 *      atan2(y,x)             -> ideal reference
 *      cordic_goldenModel()   -> hardware-oriented CORDIC model
 *
 * Therefore the error measured here belongs only to the CORDIC model:
 *
 *      error = CORDIC(X,Y) - atan2(Y,X)
 *
 * The original sin/cos quantization error is NOT included.
 *
 * ================================================================================
 */

#define ITERATIONS_EXTRA       4
#define ANGLE_BITS_EXTRA       4
#define XY_BITS_EXTRA          2

#define ANGLE_STEP_DEG         0.01


static double rad_to_deg(double angle_rad)
{
	return angle_rad * 180.0 / PI;
}


static double deg_to_rad(double angle_deg)
{
	return angle_deg * PI / 180.0;
}


static double wrap_error(double error)
{
	if (error >= PI)
		error -= TWO_PI;

	if (error < -PI)
		error += TWO_PI;

	return error;
}


int main(void)
{
	unsigned input_bits;
	double target_error_deg;


	// ================================================================================
	// Get Test Parameters
	// ================================================================================

	printf("Insert the number of CORDIC input bits: ");

	if (scanf("%u", &input_bits) != 1) {
		printf("Invalid input\n");
		return 1;
	}

	if (input_bits < 2 || input_bits > 32) {
		printf("Input bits must be between 2 and 32\n");
		return 1;
	}


	printf("Insert the target maximum angular error [deg]: ");

	if (scanf("%lf", &target_error_deg) != 1) {
		printf("Invalid input\n");
		return 1;
	}

	if (target_error_deg <= 0.0) {
		printf("Target error must be greater than zero\n");
		return 1;
	}


	double target_error_rad = deg_to_rad(target_error_deg);


	// ================================================================================
	// Find Minimum Number of Iterations
	// ================================================================================

	unsigned min_iterations = 1;

	while (atan(pow(2.0, -(int)(min_iterations - 1))) > target_error_rad)
		min_iterations++;


	// ================================================================================
	// Find Minimum Fz Required by the Target Resolution
	// ================================================================================

	unsigned min_target_angle_frac_bits = 0;

	while ((0.5 * pow(2.0, -(int)min_target_angle_frac_bits)) > target_error_rad)
		min_target_angle_frac_bits++;


	printf("\nSweep starting conditions:\n");
	printf("Input bits                         = %u\n", input_bits);
	printf("Target maximum angular error       = %.8f deg\n", target_error_deg);
	printf("Minimum iterations from target     = %u\n", min_iterations);
	printf("Minimum Fz from target resolution  = %u\n\n", min_target_angle_frac_bits);


	// ================================================================================
	// Create Output CSV File
	// ================================================================================

	char executable_path[1024];
	char output_path[2048];

	ssize_t length = readlink("/proc/self/exe", executable_path, sizeof(executable_path) - 1);

	if (length < 0) {
		printf("Cannot get executable path\n");
		return 1;
	}

	executable_path[length] = '\0';

	char *last_slash = strrchr(executable_path, '/');

	if (last_slash == NULL) {
		printf("Invalid executable path\n");
		return 1;
	}

	*last_slash = '\0';

	snprintf(
		output_path,
		sizeof(output_path),
		"%s/../outputs/cordic_sweep.csv",
		executable_path
	);

	if (output_file == NULL) {
		printf("Error opening output file\n");
		return 1;
	}


	fprintf(output_file,
		"input_bits,"
		"target_error_deg,"
		"iterations,"
		"xy_frac_bits,"
		"angle_frac_bits,"
		"xy_internal_bits,"
		"angle_internal_bits,"
		"max_abs_error_deg,"
		"rms_error_deg,"
		"mean_error_deg,"
		"worst_angle_deg,"
		"worst_x,"
		"worst_y,"
		"meets_target\n"
	);


	// Use the complete positive input range for the test vector amplitude
	int32_t amplitude = (int32_t)((1LL << (input_bits - 1)) - 1);


	// ================================================================================
	// CORDIC Configuration Sweep
	// ================================================================================

	for (unsigned iterations = min_iterations;
		 iterations <= min_iterations + ITERATIONS_EXTRA;
		 ++iterations) {


		/*
		 * Minimum Fz for this number of iterations.
		 *
		 * Two conditions must be satisfied:
		 *
		 *      Fz >= minimum required by the target error
		 *      Fz >= N - 1
		 */
		unsigned min_angle_frac_bits = min_target_angle_frac_bits;

		if ((iterations - 1) > min_angle_frac_bits)
			min_angle_frac_bits = iterations - 1;


		for (unsigned angle_frac_bits = min_angle_frac_bits;
			 angle_frac_bits <= min_angle_frac_bits + ANGLE_BITS_EXTRA;
			 ++angle_frac_bits) {


			for (unsigned xy_frac_bits = 0;
				 xy_frac_bits <= iterations + XY_BITS_EXTRA;
				 ++xy_frac_bits) {


				CordicConfig config = {
					.input_bits      = input_bits,
					.iterations      = iterations,
					.xy_frac_bits    = xy_frac_bits,
					.angle_frac_bits = angle_frac_bits
				};


				double max_abs_error = 0.0;
				double sum_squared_error = 0.0;
				double sum_error = 0.0;

				double worst_angle = 0.0;

				int32_t worst_x = 0;
				int32_t worst_y = 0;

				uint64_t samples = 0;


				// ================================================================================
				// Angular Sweep
				// ================================================================================

				for (double theta_deg = -180.0;
					 theta_deg < 180.0;
					 theta_deg += ANGLE_STEP_DEG) {


					double theta_rad = deg_to_rad(theta_deg);


					int32_t x = (int32_t)llround(amplitude * cos(theta_rad));
					int32_t y = (int32_t)llround(amplitude * sin(theta_rad));


					double reference_angle = cordic_idealModel(y, x);
					double cordic_angle;


					if (!cordic_goldenModel(y, x, &config, &cordic_angle))
						continue;


					double error = wrap_error(cordic_angle - reference_angle);
					double abs_error = fabs(error);


					if (abs_error > max_abs_error) {
						max_abs_error = abs_error;

						worst_angle = theta_deg;
						worst_x = x;
						worst_y = y;
					}


					sum_error += error;
					sum_squared_error += error * error;

					samples++;
				}


				double rms_error = sqrt(sum_squared_error / samples);
				double mean_error = sum_error / samples;

				double max_abs_error_deg = rad_to_deg(max_abs_error);
				double rms_error_deg = rad_to_deg(rms_error);
				double mean_error_deg = rad_to_deg(mean_error);


				unsigned xy_internal_bits =
					input_bits + 2 + xy_frac_bits;

				unsigned angle_internal_bits =
					angle_frac_bits + 4;


				int meets_target =
					max_abs_error_deg <= target_error_deg;


				// ================================================================================
				// Print Results
				// ================================================================================

				printf(
					"N=%2u  Fxy=%2u  Fz=%2u  Max=%10.6f deg  RMS=%10.6f deg  %s\n",
					iterations,
					xy_frac_bits,
					angle_frac_bits,
					max_abs_error_deg,
					rms_error_deg,
					meets_target ? "PASS" : "FAIL"
				);


				// ================================================================================
				// Save Results
				// ================================================================================

				fprintf(output_file,
					"%u,%.12f,%u,%u,%u,%u,%u,%.12f,%.12f,%.12f,%.6f,%d,%d,%d\n",
					input_bits,
					target_error_deg,
					iterations,
					xy_frac_bits,
					angle_frac_bits,
					xy_internal_bits,
					angle_internal_bits,
					max_abs_error_deg,
					rms_error_deg,
					mean_error_deg,
					worst_angle,
					worst_x,
					worst_y,
					meets_target
				);
			}
		}
	}


	fclose(output_file);

	printf("\nSweep completed. Results saved in cordic_sweep.csv\n");

	return 0;
}