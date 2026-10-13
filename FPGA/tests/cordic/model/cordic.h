#ifndef CORDIC_H
#define CORDIC_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    unsigned int input_bits;   // Structural parameter: input signed width
	unsigned int xy_frac_bits;
	unsigned int angle_frac_bits;
    unsigned int iterations;   // Number of CORDIC micro-rotations
} CordicConfig;

double cordic_idealModel(int32_t y, int32_t x);
bool cordic_goldenModel(int32_t y, int32_t x, const CordicConfig *config, double *angle_rad);


#endif