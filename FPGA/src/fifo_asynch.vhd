	-- Both clocks use their rising edge.
	-- Writes when full and reads when empty are ignored.
	-- Each clock must run to update its local view of the other pointer.

-- In each domain (Write and Read), two versions of the FIFO pointer are used:
--	- Binary Version: This is the standard rapresentation of a pointer, and it is used inside 
--			each clock domain to access the FIFO memory cell directly!
--	- Gray Code Version: This is just an encoded version of the Binary Version on the same number
--			of bits, and esures that consecutive numbers only change one bit at each time! 
--			This encoding is used to communicate pointer values between clock domain, allowing 
--			to define conditions such as FIFO empty and FIFO full!

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fifo_asynch is
	generic (
		DATA_WIDTH : positive := 16;	
		ADDR_WIDTH : positive := 4;		-- FIFO depth = 2**ADDR_WIDTH
		SYNCH_STAGES : positive := 2	-- Stages for all synchronizers
	);
	port (
		rst_n_i : in std_logic;		-- Asynch. Reset, active Low 

		-- Write Interface
		wr_clk_i	: in		std_logic;
		wr_data_i	: in		std_logic_vector(DATA_WIDTH-1 downto 0);
		wr_push_i   : in		std_logic;
		wr_full_o	: buffer	std_logic;

		-- Read Interface
		rd_clk_i	: in		std_logic;
		rd_pop_i	: in		std_logic;		
		rd_data_o	: out		std_logic_vector(DATA_WIDTH-1 downto 0);
		rd_empty_o	: buffer	std_logic
	);
end entity fifo_asynch;


architecture rtl of fifo_asynch is

	constant FIFO_DEPTH : positive := 2**ADDR_WIDTH;

	-- The extra pointer bit tracks wrap-around.
	subtype pointer_t is unsigned(ADDR_WIDTH downto 0);
	type pointer_sync_t is array (0 to SYNCH_STAGES-1) of pointer_t;
	type memory_t is array (0 to FIFO_DEPTH-1) of std_logic_vector(DATA_WIDTH-1 downto 0);
	signal memory : memory_t;

	-- Write Pointer
	signal wr_binary, wr_binary_next   : pointer_t;
	signal wr_gray, wr_gray_next : pointer_t;

	-- Read Pointer
	signal rd_binary, rd_binary_next   : pointer_t;
	signal rd_gray, rd_gray_next : pointer_t;

	-- Read pointer synchronized to the write clock.
	signal rd_gray_wr_pipe : pointer_sync_t;
	signal rd_gray_wr_sync : pointer_t;

	-- Write pointer synchronized to the read clock.
	signal wr_gray_rd_pipe : pointer_sync_t;
	signal wr_gray_rd_sync : pointer_t;

	-- Reset release is synchronized separately for each clock.
	signal wr_reset_sync		: std_logic_vector(SYNCH_STAGES-1 downto 0);
	signal rd_reset_sync		: std_logic_vector(SYNCH_STAGES-1 downto 0);
	signal wr_rst_n, rd_rst_n	: std_logic;

begin

	-- Use at least 2 stages for synchronization.
	assert SYNCH_STAGES >= 2
		report "FIFO: SYNCH_STAGES must be at least 2"
		severity failure;

	-- ======================================================================================
	-- 			Reset handling: asynchronous assertion, synchronous release
	-- --------------------------------------------------------------------------------------
	-- Basically there is just one common Asynch. Reset from Outside the FIFO, and I need 
	-- to distribute that to both Clock Domains. The reset is applied asynchronously to both
	-- sides, but the relase of the reset needs synchronization to reach both sides
	-- ======================================================================================
	process(wr_clk_i, rst_n_i)
	begin
		if rst_n_i = '0' then
			-- Asynch applicatin of the Reset signal to the Synchronization
			-- Reset FF
			wr_reset_sync <= (others => '0');

		elsif rising_edge(wr_clk_i) then
			-- Shift the Reset Synchronizer!
			wr_reset_sync(0) <= '1';
			for stage in 1 to SYNCH_STAGES-1 loop
				wr_reset_sync(stage) <= wr_reset_sync(stage-1);
			end loop;
		end if;
	end process;

	process(rd_clk_i, rst_n_i)
	begin
		if rst_n_i = '0' then
			-- Asynch applicatin of the Reset signal to the Synchronization
			-- Reset FF
			rd_reset_sync <= (others => '0');

		elsif rising_edge(rd_clk_i) then
			-- Shift the Reset Synchronizer!
			rd_reset_sync(0) <= '1';
			for stage in 1 to SYNCH_STAGES-1 loop
				rd_reset_sync(stage) <= rd_reset_sync(stage-1);
			end loop;
		end if;
	end process;

	-- Define the actual reset signal to be used in the two Clock Domains
	-- These are just the synchronized version of the original signal in each clock domain
	wr_rst_n <= wr_reset_sync(SYNCH_STAGES-1);
	rd_rst_n <= rd_reset_sync(SYNCH_STAGES-1);




	-- Next Write Pointer: Increment the pointer IF a FIFO push is applied and if the FIFO is 
	-- NOT full. Then transform the pointer in Gray Code to be synchronized to the other clock 
	-- domain
	wr_binary_next	<=	wr_binary + 1	when	(wr_push_i = '1')	and 
												(wr_full_o = '0')	else 
						wr_binary;
	wr_gray_next	<=	wr_binary_next	xor	shift_right(wr_binary_next, 1);

	-- Write domanin sequential processes
	process(wr_clk_i, wr_rst_n)
		variable full_pointer : pointer_t;
	begin
		if wr_rst_n = '0' then
			wr_binary 	<= (others => '0');
			wr_gray		<= (others => '0');
			wr_full_o	<= '1';				-- FIFO is considered Full, as the "safest" option, because the writes are blocked up until the FIFO is considered NOT full explicitly!!
		
		elsif rising_edge(wr_clk_i) then
			-- Update the pointers (binary and Gray versions)
			wr_binary	<= wr_binary_next;
			wr_gray		<= wr_gray_next;

			-- Invert the two highest Gray bits to check for a full FIFO.
			full_pointer				:= rd_gray_wr_sync;
			full_pointer(ADDR_WIDTH)	:= not (rd_gray_wr_sync(ADDR_WIDTH));
			full_pointer(ADDR_WIDTH-1)	:= not (rd_gray_wr_sync(ADDR_WIDTH-1));
			
			-- Check if the FIFO is full, and so if the FIFO can accept new writes!
			if wr_gray_next = full_pointer then
				wr_full_o <= '1';
			else
				wr_full_o <= '0';
			end if;

		end if;
	end process;


	-- Next Read Pointer: Increment the pointer IF a FIFO pop is applied and if the FIFO is 
	-- NOT empty. Then transform the pointer in Gray Code to be synchronized to the other clock 
	-- domain
	rd_binary_next	<=	rd_binary + 1	when	(rd_pop_i = '1')	and 
												(rd_empty_o = '0')	else 
						rd_binary;
	rd_gray_next	<=	rd_binary_next xor shift_right(rd_binary_next, 1);

	-- Read Pointer and Empty Flag
	process(rd_clk_i, rd_rst_n)
	begin
		if rd_rst_n = '0' then
			rd_binary	<= (others => '0');
			rd_gray		<= (others => '0');
			rd_empty_o	<= '1';

		elsif rising_edge(rd_clk_i) then
			rd_binary	<= rd_binary_next;
			rd_gray		<= rd_gray_next;
			
			if rd_gray_next = wr_gray_rd_sync then
				rd_empty_o <= '1';
			else
				rd_empty_o <= '0';
			end if;
		end if;
	end process;

	-- Synchronize the registered Gray pointers, not the binary pointers.
	-- Apply CDC timing constraints to these paths in the FPGA project.
	process(wr_clk_i, wr_rst_n)
	begin
		if wr_rst_n = '0' then
			rd_gray_wr_pipe <= (others => (others => '0'));
		elsif rising_edge(wr_clk_i) then
			rd_gray_wr_pipe(0) <= rd_gray;
			for stage in 1 to SYNCH_STAGES-1 loop
				rd_gray_wr_pipe(stage) <= rd_gray_wr_pipe(stage-1);
			end loop;
		end if;
	end process;

	process(rd_clk_i, rd_rst_n)
	begin
		if rd_rst_n = '0' then
			wr_gray_rd_pipe <= (others => (others => '0'));
		elsif rising_edge(rd_clk_i) then
			wr_gray_rd_pipe(0) <= wr_gray;
			for stage in 1 to SYNCH_STAGES-1 loop
				wr_gray_rd_pipe(stage) <= wr_gray_rd_pipe(stage-1);
			end loop;
		end if;
	end process;

	rd_gray_wr_sync <= rd_gray_wr_pipe(SYNCH_STAGES-1);
	wr_gray_rd_sync <= wr_gray_rd_pipe(SYNCH_STAGES-1);

	-- Write the memory. Resetting the pointers is enough; memory is not reset.
	process(wr_clk_i)
	begin
		if rising_edge(wr_clk_i) then
			if (wr_rst_n = '1') and (wr_push_i = '1') and (wr_full_o = '0') then
				memory(to_integer(wr_binary(ADDR_WIDTH-1 downto 0))) <= wr_data_i;
			end if;
		end if;
	end process;

	-- FWFT: the current word is visible before asserting rd_pop_i.
	-- Data is valid only when rd_empty_o = '0'.
	-- This version uses a combinatorial memory read.
	rd_data_o <= memory(to_integer(rd_binary(ADDR_WIDTH-1 downto 0)))
		when (rd_empty_o = '0') and (rd_rst_n = '1') else (others => '0');

end architecture rtl;
