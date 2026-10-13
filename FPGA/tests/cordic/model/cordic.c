#include "cordic.h"

#include <math.h>
#include <stddef.h>
#include <stdint.h>

#define CORDIC_PI       3.141592653589793238462643383279502884

double cordic_idealModel(int32_t y, int32_t x)
{
    if (x == 0 && y == 0)
        return NAN;

    return atan2((double)y, (double)x);
}

// Check whether an input value fits in a signed input_bits representation.
static bool input_fits(int32_t value, unsigned input_bits)
{
    if (input_bits < 1 || input_bits > 32)
        return false;

    int64_t min_value = -(1LL << (input_bits - 1));
    int64_t max_value =  (1LL << (input_bits - 1)) - 1;

    return ((int64_t)value >= min_value) &&
           ((int64_t)value <= max_value);
}


bool cordic_goldenModel(int32_t y, int32_t x, const CordicConfig *config, double *angle_rad) {

    // Sanity check on the inputs of the model (if inputs are not OK, just quit with error code!!)
    if (    angle_rad == NULL										||	// Check if the pointer where to write the result is valid
            config == NULL											||	// Check that the CORDIC config pointer is valid
			config->input_bits < 1 || config->input_bits > 32		||	// Check that the input bits value is rapresentable in this model (int32_t) and it is != 0
            config->iterations == 0 || config->iterations > 64		||	// Check that CORDIC performs at least 1 iteration and it is applicable (X and Y are 64 bits, so I can not shift more)
			config->xy_frac_bits + config->input_bits + 2 > 64		||	// Check that the total number of X and Y bits is rapresentable by this model (64 bits integers are used)
			config->angle_frac_bits + 4 > 64						||	// Check that the total number of Angle bits is rapresentable by this model (64 bits integers are used)
			!input_fits(x, config->input_bits)						||	// Check that the CORDIC input X is rapresentable with the number of bits defined for CORDIC
            !input_fits(y, config->input_bits)						||	// Check that the CORDIC input Y is rapresentable with the number of bits defined for CORDIC
            ((x == 0) && (y == 0)))				{	// Check that X (cos(theta)) and Y (sin(theta)) are plausible (there is no angle with sin = 0 and cos = 0)
        return false;
    }

	// ================================================================================
	// Set the Initial values of the CORDIC Algorithm
	// ================================================================================

	// Transofrm the input binary integer values X and Y into a fixed point number 
	// with xy_frac_bits fractional bits and the same value. The transformation is:
	//
	// 	 N bit		   N bit   fract. bits
	// ----------     ---------- -----------	
	// XXXXXXXXXX --> XXXXXXXXXX.00000000000
	int64_t xi = (int64_t)x << config->xy_frac_bits;
	int64_t yi = (int64_t)y << config->xy_frac_bits;

	// Transofrm the input binary integer values X and Y into a fixed point number 
	// with "iterations" fractional bits and the same value. This is because at each iteration, 
	// the angle is shifted  
	// The transformation is the same as the one above
	int64_t zi = 0;				// Starting Angle of the vector = 0

	// Normalize the input angle, because CORDIC works correctly with angles in the range 
	// [-90°; +90°]. If the input sin and cos generate an angle that is NOT in that range,
	// I just need to normalize (just change the sign of both cos and sin, and based on the
	// starting quadrant of the angle (Defined via the starting signs of cos and sin), decide
	// if the final angle should be added or subtracted pi)	
	int64_t pi_fixed = llround(CORDIC_PI * (1LL<< config->angle_frac_bits));	
    int64_t two_pi_fixed = llround((2.0 * CORDIC_PI) * (1LL << config->angle_frac_bits));
	if (xi < 0) {
        xi = -xi;
        yi = -yi;
		
        if (y >= 0) {
			zi = pi_fixed;
		} else{
            zi = -pi_fixed;
		}
	}
    
    // Apply the following Algo (CORDIC) for "iterations" times:
    //     x(i+1) = x(i) + d * y(i) * 2^-i
    //     y(i+1) = y(i) - d * x(i) * 2^-i
    //     z(i+1) = z(i) + d * atan(2^-i)
    // with: d = sign(y)
    for (unsigned i = 0; i < config->iterations; ++i) {

        int64_t x_shift = xi >> i;	// Compute: x(i) * 2^-i (shift must be arithmentic)
        int64_t y_shift = yi >> i;	// Compute: y(i) * 2^-i (shift must be arithmentic)


        // Define the atan(2^-i) value
		// This value is a const, and in the real HW implementation will be saved in a LUT
        double atan_value = atan(pow(2.0, -(int)i));

		// Transform the Floating Point version of atan(2^-i) into a Fixed Point version 
		// into a Fixed Point (with the correct number of fractional bits)
        int64_t atan_fixed = llround(atan_value * (1LL << config->angle_frac_bits));


        int64_t next_x;
        int64_t next_y;

		// Check the Y value (sin) of the current iteration. 
		// The objective is to put Y to zero (because I start from an angle Theta and I tend
		// an angle of 0 --> Y = sin = 0, in order to evaluate the angle Theta) 
        // In practice the sign of the sin of the vector of the current iteration gives info
		// about the the direction of the next movement to be done (if we are under 0° I need
		// to move in anti-clock wise (d = 1), and in the other case I need to move clcok-wise
		// (d = -1))
		if (yi >= 0) {
			// d = 1
            next_x	= xi + y_shift;
            next_y	= yi - x_shift;
            zi		+= atan_fixed;
        } else {
			// d = -1
            next_x	= xi - y_shift;
            next_y	= yi + x_shift;
            zi		-= atan_fixed;
        }

		// Update the X and Y values with the next iteration values
        xi = next_x;
        yi = next_y;
    }


    // Make sure the output value is in the range -180°; +180°
	// This situation can happen input sin and cos that points to an angle very 
	// similar to 180°, where the Fixed Point computations errors can induce an
	// out of range result
    if (zi >= pi_fixed)
        zi -= two_pi_fixed;

    else if (zi < -pi_fixed)
        zi += two_pi_fixed;

	// Transform the output Angle Value from Fixed Point to Floating Point
	// so the result is understandable outside this function!
    *angle_rad = (double)zi / (double)(1LL << config->angle_frac_bits);

    return true;
}
