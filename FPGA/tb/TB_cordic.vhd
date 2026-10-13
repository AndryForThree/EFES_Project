library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library std;
use std.textio.all;
use std.env.all;


entity tb_cordic is
    generic (
        TB_INPUT_BITS          : positive := 12;
        TB_ITERATIONS          : positive := 16;
        TB_XY_FRAC_BITS        : natural  := 4;
        TB_ANGLE_FRAC_BITS     : natural  := 16;
        TB_TIMEOUT_CYCLES      : positive := TB_ITERATIONS + 4;

        INPUT_VECTOR_PATH   : string := "vectors/input_vectors.txt";
        GOLDEN_OUTPUT_PATH  : string := "vectors/golden_outputs.txt";

        CLK_PERIOD          : time := 20 ns
    );
end entity tb_cordic;


architecture tb of tb_cordic is

    signal TB_clk       : std_logic := '0';
    signal TB_rst       : std_logic := '1';
    signal TB_valid_i   : std_logic := '0';
    signal TB_x_i       : signed ((TB_INPUT_BITS-1) downto 0) := (others => '0');
    signal TB_y_i       : signed ((TB_INPUT_BITS-1) downto 0) := (others => '0');
    signal TB_angle_o   : signed ((TB_ANGLE_FRAC_BITS+3) downto 0);
    signal TB_busy_o    : std_logic;
    signal TB_ready_o   : std_logic;
    signal TB_valid_o   : std_logic;
    signal TB_invalid_o : std_logic;

begin


    -- ============================================================================
    -- Clock Generation
    -- ============================================================================
    TB_clk <= not TB_clk after CLK_PERIOD / 2;


    -- ============================================================================
    -- DUT
    -- ============================================================================
    DUT : entity work.cordic
        generic map (
            INPUT_BITS      => TB_INPUT_BITS,
            ITERATIONS      => TB_ITERATIONS,
            XY_FRAC_BITS    => TB_XY_FRAC_BITS,
            ANGLE_FRAC_BITS => TB_ANGLE_FRAC_BITS
        )
        port map (
            clk				=> TB_clk,
            rst				=> TB_rst,
            valid_i			=> TB_valid_i,
            x_i				=> TB_x_i,
            y_i				=> TB_y_i,
            angle_o			=> TB_angle_o,
            busy_o			=> TB_busy_o,
            ready_o			=> TB_ready_o,
            valid_o			=> TB_valid_o,
            invalid_o		=> TB_invalid_o
        );


    -- ============================================================================
    -- Stimulus + Bit-Exact Checker
    -- ============================================================================

    test_process : process

        file input_file			: text;
        file golden_file		: text;

        variable input_status  : file_open_status;
        variable golden_status : file_open_status;

        variable input_line  : line;	-- Current input vector File line
        variable golden_line : line;	-- Current Golden Model output file line

        variable x_value 	: integer;	-- Current Input X value read from the current Input Vector File line
        variable y_value 	: integer;	-- Current Input Y value read from the current Input Vector File line

        variable goldModel_angle_int   : integer;
		variable goldModel_invalid_int : integer;

		variable goldModel_angle       : signed(TB_ANGLE_FRAC_BITS+3 downto 0);
		variable goldModel_invalid     : std_logic;

        variable input_count : natural := 0;
        variable test_count  : natural := 0;
        variable error_count : natural := 0;

        variable aborted       : boolean := false;
        variable wait_cycles   : natural;
        variable good          : boolean;
        variable line_valid    : boolean;
        variable expected_output_cycle : positive;

        procedure check_controls(
            constant expected_ready : in std_logic;
            constant expected_busy  : in std_logic;
            constant expected_valid : in std_logic
        ) is
        begin
            if TB_ready_o /= expected_ready or
               TB_busy_o /= expected_busy or
               TB_valid_o /= expected_valid then
                report "PROTOCOL MISMATCH - input " & integer'image(input_count) &
                    " | ready/busy/valid expected = " &
                    std_logic'image(expected_ready) & "/" &
                    std_logic'image(expected_busy) & "/" &
                    std_logic'image(expected_valid) &
                    " | actual = " & std_logic'image(TB_ready_o) & "/" &
                    std_logic'image(TB_busy_o) & "/" &
                    std_logic'image(TB_valid_o)
                    severity warning;
                error_count := error_count + 1;
            end if;
        end procedure;

    begin

        -- Open file with Input Vector
        file_open(input_status, input_file, INPUT_VECTOR_PATH, read_mode);
        assert input_status = open_ok
            report "TB ERROR: cannot open input vector file: " & INPUT_VECTOR_PATH
            severity failure;

		-- Open file with Output Vector of Golden Model
        file_open(golden_status, golden_file, GOLDEN_OUTPUT_PATH, read_mode);
        assert golden_status = open_ok
            report "TB ERROR: cannot open Golden Model output file: " & GOLDEN_OUTPUT_PATH
            severity failure;
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      
        -- Reset to start the Unit to a known state
        TB_rst     <= '1';
        TB_valid_i <= '0';
        for i in 1 to 3 loop
            wait until rising_edge(TB_clk);
        end loop;
        TB_rst <= '0';
        wait until rising_edge(TB_clk);
        wait until falling_edge(TB_clk);
        check_controls('1', '0', '0');


        -- Run all test vectors from the Input Vector file
        vector_loop : while not endfile(input_file) loop
            -- Read next input from Input Vector file
            readline(input_file, input_line);
            input_count := input_count + 1;
			line_valid := true;

			read(input_line, x_value, good);
			if not good then
				report "TB ERROR: cannot read X value"
					severity warning;
				line_valid := false;
			end if;

			read(input_line, y_value, good);
			if not good then
				report "TB ERROR: cannot read Y value"
					severity warning;
				line_valid := false;
			end if;

			-- Read the expected output from the Golden Model ouput file
			if endfile(golden_file) then
                report
                    "TB ERROR: Golden Model output missing for sample " &
                    integer'image(input_count)
                    severity warning;

                line_valid := false;
			else 
				readline(golden_file, golden_line);
                
				read(golden_line, goldModel_angle_int, good);
				if not good then
					report "TB ERROR: cannot read golden angle value"
						severity warning;
					line_valid := false;
				end if;
				

                read(golden_line, goldModel_invalid_int, good);
				if not good then
					report "TB ERROR: cannot read golden invalid value"
						severity warning;
					line_valid := false;
                elsif goldModel_invalid_int /= 0 and goldModel_invalid_int /= 1 then
                    report "TB ERROR: golden invalid value must be 0 or 1"
                        severity warning;
                    line_valid := false;
				end if;
			end if;

			-- Check if there are valid inputs and golden model outputs for the current Input Vector line
			if line_valid = true then 
				-- Transform the Golden Model values read (integer) into bit and bit vectors
				goldModel_angle := to_signed(goldModel_angle_int, goldModel_angle'length);
				
				if goldModel_invalid_int = 0 then
				    goldModel_invalid := '0';
				elsif goldModel_invalid_int = 1 then
				    goldModel_invalid := '1';
				end if;

				-- Wait until the CORDIC can accept a new input
                wait_cycles := 0;
                while TB_ready_o /= '1' loop
                    if wait_cycles = TB_TIMEOUT_CYCLES then
                        report "TB ABORT: DUT stuck waiting for ready_o - input " &
                            integer'image(input_count) & " | timeout after " &
                            integer'image(wait_cycles) & " cycles"
                            severity warning;
                        error_count := error_count + 1;
                        aborted := true;
                        exit vector_loop;
                    end if;
                    wait until rising_edge(TB_clk);
                    wait_cycles := wait_cycles + 1;
                end loop;

				check_controls('1', '0', '0');
                -- At rising edges we sample the signals before the DUT updates.
                -- A normal result is observed after ITERATIONS + 1 edges;
                -- the zero vector goes directly to OUTPUT, observed after 1 edge.
                if x_value = 0 and y_value = 0 then
                    expected_output_cycle := 1;
                else
                    expected_output_cycle := TB_ITERATIONS + 1;
                end if;

				-- Send input to the Device Under Test
				TB_x_i     <= to_signed(x_value, TB_INPUT_BITS);
				TB_y_i     <= to_signed(y_value, TB_INPUT_BITS);
				TB_valid_i <= '1';
				wait until rising_edge(TB_clk);
				TB_valid_i <= '0';

				-- Wait for output
                for cycle in 1 to TB_TIMEOUT_CYCLES loop
                    wait until rising_edge(TB_clk);
                    if TB_valid_o = '1' then
                        check_controls('1', '0', '1');
                        if cycle /= expected_output_cycle then
                            report "LATENCY MISMATCH - input " & integer'image(input_count) &
                                " | expected cycles = " & integer'image(expected_output_cycle) &
                                " | actual cycles = " & integer'image(cycle)
                                severity warning;
                            error_count := error_count + 1;
                        end if;
                        exit;
                    end if;
                    check_controls('0', '1', '0');
                end loop;

                if TB_valid_o /= '1' then
                    report "TB ABORT: DUT stuck waiting for valid_o - input " &
                        integer'image(input_count) & " | timeout after " &
                        integer'image(TB_TIMEOUT_CYCLES) & " cycles"
                        severity warning;
                    error_count := error_count + 1;
                    aborted := true;
                    exit vector_loop;
                end if;
				test_count := test_count + 1;
            	

				-- Output comparison between the Golden Model output and the actual output
				-- generated by the LUT
				-- Compare the Angle ONLY IF the invalid bit is not set (basically compare the 
				-- angle only it is valid and so it is reliable)!
				if (goldModel_invalid /= TB_invalid_o) then
					assert false 	report
										"INVALID MISMATCH - sample " &
										integer'image(test_count) &
										" | X = " & integer'image(x_value) &
										" | Y = " & integer'image(y_value) &
										" | Golden invalid = " & integer'image(goldModel_invalid_int) &
										" | DUT invalid = " & std_logic'image(TB_invalid_o)
									severity warning;
					error_count := error_count + 1;

				-- If both models agree that the angle is valid, perform the bit-exact comparison
				elsif TB_invalid_o = '0' then
					if TB_angle_o /= goldModel_angle then
						assert false	report	"ANGLE MISMATCH - sample " &
												integer'image(test_count) &
												" | X = " & integer'image(x_value) &
												" | Y = " & integer'image(y_value) &
												" | Golden angle = " & integer'image(goldModel_angle_int) &
												" | DUT angle = " & integer'image(to_integer(TB_angle_o))
										severity warning;
						error_count := error_count + 1;
					end if;
				end if;

                -- No new request was sent in OUTPUT: by the next falling edge
                -- the DUT must be idle again, with valid_o deasserted.
                wait until falling_edge(TB_clk);
                check_controls('1', '0', '0');
			else
				error_count := error_count + 1;
			end if;
		end loop;

        -- Remaining golden outputs are expected when the run was aborted, so do not check the
		-- Golden Model output file in that case
        if not aborted then
            -- Check that Golden Model file has no additional results
            while not endfile(golden_file) loop
                readline(golden_file, golden_line);
                error_count := error_count + 1;
                report "TB ERROR: Golden Model contains more outputs than input vectors"
                    severity warning;
            end loop;
        end if;

        -- Close the files and write the Final Report
        file_close(input_file);
        file_close(golden_file);

        if test_count = 0 then
            report "TB ERROR: no samples checked"
                severity warning;
            error_count := error_count + 1;
        end if;

        report	"============================================================"
            	severity note;

        if aborted then
            report "CORDIC TB aborted early: DUT stuck" severity note;
        end if;
        report "CORDIC TB report: " &
            integer'image(input_count) & " inputs considered, " &
            integer'image(test_count) & " outputs checked, " &
            integer'image(error_count) & " errors (including timeouts)"
            severity note;

        if error_count = 0 then
            report	"CORDIC TB RESULT: PASS"
                	severity note;
            report	"============================================================"
                	severity note;
            finish;
        else
            report	"============================================================"
                	severity note;

            assert false	report
                    		"CORDIC TB RESULT: FAIL - " &
                    		integer'image(error_count) &
                    		" error(s)"
                			severity failure;
        end if;
        wait;
    end process;
end architecture tb;
