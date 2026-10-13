library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;


entity cordic is
    generic (
        INPUT_BITS		: positive := 12;	-- Number of Bits of the input valuds X and Y 	
        ITERATIONS		: positive := 16;	-- Number of interal CORDIC iterations to be performed
        XY_FRAC_BITS	: natural  := 4;	-- Number of fractional bits used in the internal Fixed POint notation of X and Y
        ANGLE_FRAC_BITS	: natural  := 16	-- Number of fractional bits used in the internal Fixed POint notation of output angle
    );
    port (
        clk			: in	std_logic;
        rst			: in	std_logic;	-- Synch. Reset, active high
        valid_i		: in	std_logic;	-- Input Control Signal: defines if the input values are valid
		x_i			: in	signed ((INPUT_BITS-1) downto 0);		-- Data Input: cos (angle_o)			 
        y_i			: in	signed ((INPUT_BITS-1) downto 0);		-- Data Input: sin (angle_o)
        angle_o		: out	signed ((ANGLE_FRAC_BITS+3) downto 0);	-- Data Output: Angle associated with the input cos and sin 
        busy_o		: out	std_logic;	-- Output Control Signal: Defines if the CORDIC is processing some inputs
        ready_o		: out	std_logic;	-- Output Control Signal: Defines if the CORDIC is ready to accept a new input request
		valid_o		: out	std_logic;	-- Output Control Signal: Defines if the output data is valid
		invalid_o	: out	std_logic	-- Output Control Signal: input vector (0,0), angle undefined
	);
end entity cordic;


architecture rtl of cordic is

    -- ============================================================================
    -- Internal Widths
    -- ============================================================================
	constant XY_GUARD_BITS	: integer := 2;
    constant XY_WIDTH 		: positive := INPUT_BITS + XY_GUARD_BITS + XY_FRAC_BITS;
    constant ANGLE_WIDTH	: positive := ANGLE_FRAC_BITS + 4;


    -- ============================================================================
    -- State Machine
    -- ============================================================================
    type state_t is (
        IDLE,		
        ITERATE,		
        OUTPUT		
    );
    signal state		: state_t;
	signal nextState	: state_t;

	-- ============================================================================
    -- Control Unit signals
    -- ============================================================================
    signal load_inputs	: std_logic;
	signal iterate_en	: std_logic;
	signal input_invalid : std_logic;

    -- ============================================================================
    -- CORDIC Registers
    -- ============================================================================
    signal x_reg 			: signed((XY_WIDTH-1)		downto 0);
    signal y_reg 			: signed((XY_WIDTH-1)		downto 0);
    signal z_reg 			: signed((ANGLE_WIDTH-1)	downto 0);
	signal invalid_reg  	: std_logic;


    -- ============================================================================
    -- Iteration Counter
    -- ============================================================================
    constant ITER_CNT_WIDTH : positive := integer(maximum(1.0, ceil(log2(real(ITERATIONS)))));
	signal iteration 		: unsigned(ITER_CNT_WIDTH-1 downto 0);

	-- ============================================================================
    -- arctan LUT
    -- ============================================================================
	type atan_lut_t is array (0 to ITERATIONS-1) of signed((ANGLE_WIDTH-1) downto 0);

	function generate_atan_lut return atan_lut_t is
		variable lut			: atan_lut_t;	-- LUT to be generated and send to the output
		variable atan_value		: real;			-- arctan value in Floating Point notation
		variable atan_fixed		: integer;		-- arctan value in Fixed Point notation
	begin
		for i in 0 to ITERATIONS-1 loop
			-- Compute the arctan in Real Numbers (Floating Point)
			atan_value := arctan(2.0 ** (-i));

			-- Convert the arctan result into the Fixed Point notation used inside the
			-- CORDIC
			atan_fixed := integer(atan_value * (2.0 ** ANGLE_FRAC_BITS));

			-- Save the Fixed Point value in the LUT
			lut(i) := to_signed(atan_fixed, ANGLE_WIDTH);
		end loop;
		return lut;
	end function;

	constant ATAN_LUT : atan_lut_t := generate_atan_lut;

	-- ============================================================================
    -- PI definition
    -- ============================================================================
	constant PI_FIXED : signed((ANGLE_WIDTH-1) downto 0) :=
    					to_signed(
    					    integer(MATH_PI * (2.0 ** ANGLE_FRAC_BITS)),
    					    ANGLE_WIDTH
    					);

	constant TWO_PI_FIXED : signed((ANGLE_WIDTH-1) downto 0) :=
                        to_signed(
                            integer((2.0 * MATH_PI) * (2.0 ** ANGLE_FRAC_BITS)),
                            ANGLE_WIDTH
                        );

begin

    -- ============================================================================
    -- State Register
    -- ============================================================================
    state_register : process(clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                state <= IDLE;
            else
                state <= nextState;
            end if;
        end if;
    end process;


    -- ============================================================================
    -- Moore Control Unit
    -- ============================================================================
    control_logic : process(all)
    begin
        -- Default control values
        ready_o     <= '0';
		busy_o		<= '0';
        valid_o     <= '0';
        load_inputs <= '0';
        iterate_en  <= '0';
		invalid_o	<= '0';

        case state is
            -- Waiting for a new input sample
            when IDLE =>
                ready_o     <= '1';
                load_inputs <= '1';

            -- Execute one CORDIC micro-rotation per clock cycle
            when ITERATE =>
                iterate_en	<= '1';
				busy_o		<= '1';

            -- Output data is valid and remains valid until accepted
            when OUTPUT =>
                valid_o 	<= '1';
				ready_o     <= '1';
                load_inputs <= '1';
				invalid_o	<= invalid_reg;
        end case;
    end process;


    -- ============================================================================
    -- Next State Logic
    -- ============================================================================

    next_state_logic : process(all)
    begin

        -- Default: remain in the current state
        nextState <= state;

        case state is

            -- Input is accepted only when valid_i = 1.
            -- ready_o is always high in this state.
            when IDLE =>
                if valid_i = '1' then
                    if input_invalid = '1' then
						nextState <= OUTPUT;
					else
						nextState <= ITERATE;
					end if;
                end if;

            -- Remain in ITERATE until the last CORDIC iteration is executed.
            when ITERATE =>
                if iteration = to_unsigned(ITERATIONS - 1, ITER_CNT_WIDTH) then
                    nextState <= OUTPUT;
                end if;

			-- After one cycle where the outputs are presented, move to idle if no
			-- additional request is presented, and move to iteration if a new request
			-- is presented
            when OUTPUT =>
				if valid_i = '0' then
					nextState <= IDLE;

				elsif input_invalid = '1' then
					nextState <= OUTPUT;

				else
					nextState <= ITERATE;
				end if;
		end case;
    end process;


    -- ============================================================================
    -- CORDIC Datapath
    -- ============================================================================
	
	input_invalid	<=	'1' when	(x_i = to_signed(0, INPUT_BITS))	and
								(y_i = to_signed(0, INPUT_BITS))	else 
					'0';
	

	datapath : process(clk)
		variable x_fixPoint : signed((XY_WIDTH-1) downto 0);
		variable y_fixPoint : signed((XY_WIDTH-1) downto 0);
		variable x_shift	: signed((XY_WIDTH-1) downto 0);
		variable y_shift	: signed((XY_WIDTH-1) downto 0);
	begin
		if rising_edge(clk) then
			if rst = '1' then
				x_reg     	<= (others => '0');
				y_reg     	<= (others => '0');
				z_reg     	<= (others => '0');
				iteration 	<= (others => '0');
				invalid_reg <= '0';

            else

                -- ================================================================
                -- Input Loading and Quadrant Normalization
                -- ================================================================
                if (load_inputs = '1') then

					invalid_reg <= input_invalid;

                    -- Convert input values (integers) to the internal fixed-point format
                    -- Example (with XY_FRAC_BITS = 4 and XY_GUARD_BITS = 2):
                    --      101101   ->   11 101101.0000
                    x_fixPoint := shift_left(resize(x_i, XY_WIDTH), XY_FRAC_BITS);
					y_fixPoint := shift_left(resize(y_i, XY_WIDTH), XY_FRAC_BITS);

                    -- Quadrant Normalization
                    -- The CORDIC core works with cos (angle_o) >=, so basically it works in the 
					-- angle range [-pi/2; pi/2] = [-90°; +90°]
					-- If practice, if the input angle is not in this range, a normalization is needed
					-- to place the initial vector in that allowed range. 
					-- This is done by changing sign to both the X (cos) and Y (sin) inputs, basically
					-- finding the vector that is symmatric in respect to the origin of axis of the 
					-- input one. Basically the vector, moved by +- pi.
					-- Obviously, the normalization moves the vector, and so the algo needs to remember
					-- this movement, by just intializing the angle accumulator Z. 
                    if (x_i < 0) then
						-- The vector is outside the allowed starting angle range, so move it by 180° by
						-- changing sign to both its sin and cos
                        x_reg <= -x_fixPoint;
                        y_reg <= -y_fixPoint;

						-- Save the initial offset introduced by the rotation in the angle accumulator Z
                        if (y_i >= 0) then
                            z_reg <= PI_FIXED;
                        else
                            z_reg <= -PI_FIXED;
                        end if;
                    else
						-- The input vector is inside the allowed range, so it can be directly fed into
						-- the iterative CORDIC algo!
                        x_reg	<= x_fixPoint;
                        y_reg	<= y_fixPoint;
                        z_reg	<= (others => '0');
                    end if;

					-- initialize the iteration counter
                    iteration <= (others => '0');

                -- ================================================================
                -- CORDIC Iteration
                -- ================================================================
				elsif iterate_en = '1' then

					-- Compute shifted versions of X and Y.
					-- Since x_reg and y_reg are signed, shift_right performs an arithmetic shift.
					x_shift := shift_right(x_reg, to_integer(iteration));	-- x_reg * 2^(-i)
					y_shift := shift_right(y_reg, to_integer(iteration));	-- y_reg * 2^(-i)

					-- Select the rotation direction in order to drive Y toward zero
					-- To do that, just check the sign bit (MSB) of the Y value
					if y_reg(XY_WIDTH-1) = '0' then
						-- Y >= 0 --> sin(Z) >= 0 --> Move vector in clockwise direction
						x_reg <= x_reg + y_shift;
						y_reg <= y_reg - x_shift;
						z_reg <= z_reg + ATAN_LUT(to_integer(iteration));
					else
						-- Y < 0 --> sin(Z) < 0 --> Move vector in anti-clockwise direction
						x_reg <= x_reg - y_shift;
						y_reg <= y_reg + x_shift;
						z_reg <= z_reg - ATAN_LUT(to_integer(iteration));
					end if;

					-- Increment the iteration count
					iteration <= iteration + 1;
				end if;
            end if;
        end if;
    end process;


    -- ============================================================================
    -- Output Angle
    -- ============================================================================
	angle_o <= z_reg - TWO_PI_FIXED when z_reg >= PI_FIXED else
			z_reg + TWO_PI_FIXED when z_reg < -PI_FIXED else
			z_reg;


end architecture rtl;