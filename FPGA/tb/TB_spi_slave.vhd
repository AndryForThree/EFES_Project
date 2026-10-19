library ieee;
use ieee.std_logic_1164.all;

entity tb_spi_slave is
    generic (
        TB_DATA_WIDTH : positive := 16;
        TB_CPOL       : boolean := false;
        TB_CPHA       : boolean := false;
        TB_LSB_FIRST  : boolean := false;
        TB_SCLK_PERIOD : time := 100 ns
    );
end entity tb_spi_slave;

architecture tb of tb_spi_slave is

    subtype word_t is std_logic_vector(TB_DATA_WIDTH-1 downto 0);
    constant HALF_PERIOD : time := TB_SCLK_PERIOD / 2;
    constant ZERO_WORD : word_t := (others => '0');

    -- Repeat the pattern if the word is wider than 16 bits.
    function make_word(pattern : std_logic_vector(15 downto 0)) return word_t is
        variable result : word_t;
    begin
        for i in result'range loop
            result(i) := pattern(i mod 16);
        end loop;
        return result;
    end function;

    constant MASTER_WORD_A : word_t := make_word(x"6B92");
    constant MASTER_WORD_B : word_t := make_word(x"39E7");
    constant SLAVE_WORD_A  : word_t := make_word(x"A53C");
    constant SLAVE_WORD_B  : word_t := make_word(x"D268");

    function idle_clock return std_logic is
    begin
        if TB_CPOL then
            return '1';
        else
            return '0';
        end if;
    end function;

    signal TB_rst_n_i       : std_logic := '0';
    signal TB_spi_sclk_i    : std_logic := idle_clock;
    signal TB_spi_cs_n_i    : std_logic := '1';
    signal TB_spi_mosi_i    : std_logic := '0';
    signal TB_spi_miso_o    : std_logic;

    signal TB_tx_data_i     : std_logic_vector(TB_DATA_WIDTH-1 downto 0) := (others => '0');
    signal TB_tx_valid_i    : std_logic := '0';
    signal TB_tx_request_o  : std_logic;

    signal TB_rx_data_o     : std_logic_vector(TB_DATA_WIDTH-1 downto 0);
    signal TB_rx_valid_o    : std_logic;

    -- Read by Tcl when the tests end.
    signal TB_done   : boolean := false;
    signal TB_passed : boolean := false;

begin

    assert HALF_PERIOD > 0 ns
        report "SPI TB: SCLK period must be positive"
        severity failure;

    -- ============================================================================
    -- DUT
    -- ============================================================================

    DUT : entity work.spi_slave
        generic map (
            DATA_WIDTH => TB_DATA_WIDTH,
            CPOL       => TB_CPOL,
            CPHA       => TB_CPHA,
            LSB_FIRST  => TB_LSB_FIRST
        )
        port map (
            rst_n_i       => TB_rst_n_i,
            spi_sclk_i    => TB_spi_sclk_i,
            spi_cs_n_i    => TB_spi_cs_n_i,
            spi_mosi_i    => TB_spi_mosi_i,
            spi_miso_o    => TB_spi_miso_o,
            tx_data_i     => TB_tx_data_i,
            tx_valid_i    => TB_tx_valid_i,
            tx_request_o  => TB_tx_request_o,
            rx_data_o     => TB_rx_data_o,
            rx_valid_o    => TB_rx_valid_o
        );

    -- ============================================================================
    -- Stimulus + Checker
    -- ============================================================================

    test_process : process
        variable test_count    : natural := 0;
        variable word_count    : natural := 0;
        variable bit_count     : natural := 0;
        variable tx_pop_count  : natural := 0;
        variable rx_word_count : natural := 0;
        variable error_count   : natural := 0;

        procedure check(constant condition : boolean; constant message_text : string) is
        begin
            if not condition then
                error_count := error_count + 1;
                assert false report message_text severity warning;
            end if;
        end procedure;

        procedure select_slave(constant data : word_t; constant valid : std_logic) is
        begin
            TB_tx_data_i <= data;
            TB_tx_valid_i <= valid;
            TB_spi_cs_n_i <= '0';
            wait for HALF_PERIOD;
        end procedure;

        procedure deselect_slave is
        begin
            TB_spi_cs_n_i <= '1';
            TB_spi_mosi_i <= '0';
            TB_tx_valid_i <= '0';
            wait for HALF_PERIOD;
            check(TB_spi_miso_o = 'Z', "MISO must be high impedance when CS is high");
            check(TB_tx_request_o = '0', "Unexpected TX pop when CS is high");
            check(TB_rx_valid_o = '0', "Unexpected RX valid when CS is high");
        end procedure;

        -- Advance the buffer only after the DUT has read its current word.
        procedure update_edge(
            constant level : std_logic;
            constant expect_pop : boolean;
            constant next_data : word_t;
            constant next_valid : std_logic
        ) is
            variable actual_pop : boolean;
        begin
            actual_pop := TB_tx_request_o = '1';
            if expect_pop then
                check(TB_tx_request_o = '1', "Missing TX pop at the first TX update edge");
            else
                check(TB_tx_request_o = '0', "Unexpected TX pop");
            end if;

            TB_spi_sclk_i <= level;
            wait for 0 ns;
            if actual_pop then
                tx_pop_count := tx_pop_count + 1;
                TB_tx_data_i <= next_data;
                TB_tx_valid_i <= next_valid;
            end if;
        end procedure;

        -- Both the master and the RX buffer acquire data on the sampling edge.
        procedure sample_edge(
            constant level : std_logic;
            constant index : natural;
            constant last_bit : boolean;
            constant expected_rx : word_t;
            variable master_received : inout word_t
        ) is
        begin
            master_received(index) := TB_spi_miso_o;
            bit_count := bit_count + 1;

            if last_bit then
                check(TB_rx_valid_o = '1', "Missing RX valid on the last bit");
                check(TB_rx_data_o = expected_rx,
                      "RX word mismatch at word " & integer'image(word_count + 1));
            else
                check(TB_rx_valid_o = '0', "RX valid before the last bit");
            end if;
            if TB_rx_valid_o = '1' then
                rx_word_count := rx_word_count + 1;
            end if;
            TB_spi_sclk_i <= level;
        end procedure;

        procedure transfer_word(
            constant master_data : word_t;
            constant expected_miso : word_t;
            constant tx_valid : boolean;
            constant next_data : word_t;
            constant next_valid : std_logic
        ) is
            variable index : natural;
            variable master_received : word_t := (others => '0');
            variable pops_before, rx_before : natural;
        begin
            pops_before := tx_pop_count;
            rx_before := rx_word_count;

            for bit_number in 0 to TB_DATA_WIDTH-1 loop
                if TB_LSB_FIRST then
                    index := bit_number;
                else
                    index := TB_DATA_WIDTH-1-bit_number;
                end if;
                TB_spi_mosi_i <= master_data(index);

                if TB_CPHA then
                    update_edge(not idle_clock, bit_number = 0 and tx_valid,
                                next_data, next_valid);
                    wait for HALF_PERIOD;
                    sample_edge(idle_clock, index, bit_number = TB_DATA_WIDTH-1,
                                master_data, master_received);
                    wait for HALF_PERIOD;
                else
                    wait for HALF_PERIOD;
                    sample_edge(not idle_clock, index, bit_number = TB_DATA_WIDTH-1,
                                master_data, master_received);
                    wait for HALF_PERIOD;
                    update_edge(idle_clock, bit_number = 0 and tx_valid,
                                next_data, next_valid);
                end if;
            end loop;

            word_count := word_count + 1;
            check(master_received = expected_miso,
                  "MISO word mismatch at word " & integer'image(word_count));
            check(rx_word_count - rx_before = 1, "Expected one RX acquisition per word");
            if tx_valid then
                check(tx_pop_count - pops_before = 1, "Expected one TX pop per valid word");
            else
                check(tx_pop_count = pops_before, "TX pop while the buffer is empty");
            end if;
        end procedure;

    begin
        wait for TB_SCLK_PERIOD;
        check(TB_spi_miso_o = 'Z', "MISO must be high impedance during reset");
        check(TB_tx_request_o = '0', "Unexpected TX pop during reset");
        check(TB_rx_valid_o = '0', "Unexpected RX valid during reset");
        TB_rst_n_i <= '1';
        wait for HALF_PERIOD;

        report "TEST 1: one word" severity note;
        select_slave(SLAVE_WORD_A, '1');
        transfer_word(MASTER_WORD_A, SLAVE_WORD_A, true, ZERO_WORD, '0');
        deselect_slave;
        test_count := test_count + 1;

        report "TEST 2: two words with CS held low" severity note;
        select_slave(SLAVE_WORD_B, '1');
        transfer_word(MASTER_WORD_B, SLAVE_WORD_B, true, SLAVE_WORD_A, '1');
        transfer_word(MASTER_WORD_A, SLAVE_WORD_A, true, ZERO_WORD, '0');
        deselect_slave;
        test_count := test_count + 1;

        report "TEST 3: empty TX buffer, RX still active" severity note;
        select_slave(SLAVE_WORD_A, '0');
        transfer_word(MASTER_WORD_B, ZERO_WORD, false, ZERO_WORD, '0');
        deselect_slave;
        test_count := test_count + 1;

        report "============================================================" severity note;
        report "SPI TB config: DATA_WIDTH=" & integer'image(TB_DATA_WIDTH) &
               ", CPOL=" & boolean'image(TB_CPOL) &
               ", CPHA=" & boolean'image(TB_CPHA) &
               ", LSB_FIRST=" & boolean'image(TB_LSB_FIRST) severity note;
        report "SPI TB report: " & integer'image(test_count) & " tests, " &
               integer'image(word_count) & " words, " &
               integer'image(bit_count) & " sampled bits, " &
               integer'image(rx_word_count) & " RX acquisitions, " &
               integer'image(tx_pop_count) & " TX pops, " &
               integer'image(error_count) & " errors" severity note;

        if error_count = 0 then
            report "SPI TB RESULT: PASS" severity note;
            TB_passed <= true;
        else
            report "SPI TB RESULT: FAIL" severity note;
        end if;
        report "============================================================" severity note;
        TB_done <= true;
        wait;
    end process;

end architecture tb;
