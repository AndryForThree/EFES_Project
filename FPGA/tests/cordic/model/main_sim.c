#include "cordic.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char *argv[])
{
    // Defaults match the generics in TB_cordic.vhd.
    CordicConfig config = {
        .input_bits = 12,
        .xy_frac_bits = 4,
        .angle_frac_bits = 16,
        .iterations = 16
    };

    // Optional arguments: NAME=VALUE. Omitted parameters keep their defaults.
    for (int i = 1; i < argc; i++) {
        char name[32];
        unsigned value;

        if (sscanf(argv[i], "%31[^=]=%u", name, &value) != 2) {
            fprintf(stderr, "Invalid parameter: %s\n", argv[i]);
            return 1;
        }

        if (strcmp(name, "INPUT_BITS") == 0)
            config.input_bits = value;
        else if (strcmp(name, "ITERATIONS") == 0)
            config.iterations = value;
        else if (strcmp(name, "XY_FRAC_BITS") == 0)
            config.xy_frac_bits = value;
        else if (strcmp(name, "ANGLE_FRAC_BITS") == 0)
            config.angle_frac_bits = value;
        else {
            fprintf(stderr, "Unknown parameter: %s\n", name);
            return 1;
        }
    }

    const int random_tests = 1000;
    const unsigned random_seed = 1;
    const int min_input = -(1 << (config.input_bits - 1));
    const int max_input = (1 << (config.input_bits - 1)) - 1;
    const int input_range = max_input - min_input + 1;

    // Each pair is {X, Y}. These cases are written before the random ones.
    const int special_cases[][2] = {
        // Origin and small vectors in all quadrants.
        {0, 0},
        {1, 0}, {-1, 0}, {0, 1}, {0, -1},
        {1, 1}, {-1, 1}, {-1, -1}, {1, -1},

        // Axis vectors at the input limits.
        {max_input, 0}, {min_input, 0},
        {0, max_input}, {0, min_input},

        // Corners of the signed input range.
        {max_input, max_input}, {min_input, max_input},
        {min_input, min_input}, {max_input, min_input},

        // Vectors close to the axes, including both sides of the +/-pi boundary.
        {max_input, 1}, {max_input, -1},
        {min_input, 1}, {min_input, -1},
        {1, max_input}, {-1, max_input},
        {1, min_input}, {-1, min_input},

        // Unequal magnitudes in all quadrants.
        {max_input, max_input / 2}, {min_input, max_input / 2},
        {min_input, min_input / 2}, {max_input, min_input / 2}
    };

    const int special_tests = sizeof(special_cases) / sizeof(special_cases[0]);
    const int total_tests = special_tests + random_tests;

    // The Bash script creates vectors/ and launches this program from outputs/sim.
    FILE *input_file = fopen("vectors/input_vectors.txt", "w");
    if (input_file == NULL) {
        perror("Cannot open vectors/input_vectors.txt");
        return 1;
    }

    FILE *golden_file = fopen("vectors/golden_outputs.txt", "w");
    if (golden_file == NULL) {
        perror("Cannot open vectors/golden_outputs.txt");
        fclose(input_file);
        return 1;
    }

    srand(random_seed);

    for (int i = 0; i < total_tests; i++) {
        int x;
        int y;

        if (i < special_tests) {
            x = special_cases[i][0];
            y = special_cases[i][1];
        } else {
            x = min_input + rand() % input_range;
            y = min_input + rand() % input_range;
        }

        long long angle_fixed = 0;
        int invalid = 0;

        if (x == 0 && y == 0) {
            invalid = 1;
        } else {
            double angle_rad;

            // The model takes its arguments in the order Y, X.
            if (!cordic_goldenModel(y, x, &config, &angle_rad)) {
                fprintf(stderr, "Golden model failed for sample %d: X=%d Y=%d\n", i + 1, x, y);
                fclose(input_file);
                fclose(golden_file);
                return 1;
            }

            // Recover the integer represented by the DUT's fixed-point output.
            angle_fixed = llround(angle_rad * (1LL << config.angle_frac_bits));
        }

        // Write both the input vector and output vector file
		// with decimal integers, without headers: one matching pair per line
		// in each file
        if (fprintf(input_file, "%d %d\n", x, y) < 0 ||
            fprintf(golden_file, "%lld %d\n", angle_fixed, invalid) < 0) {
            fprintf(stderr, "Cannot write vector files\n");
            fclose(input_file);
            fclose(golden_file);
            return 1;
        }
    }

    int input_status = fclose(input_file);
    int golden_status = fclose(golden_file);
    if (input_status != 0 || golden_status != 0) {
        fprintf(stderr, "Cannot finish writing vector files\n");
        return 1;
    }

    printf("Generated %d special cases and %d random cases (seed %u).\n",
           special_tests, random_tests, random_seed);
    printf("Files: vectors/input_vectors.txt and vectors/golden_outputs.txt\n");

    return 0;
}
