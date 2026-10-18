library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity tb_spi_slave is
    generic (
        DATA_WIDTH : positive := 8;
        CPOL       : boolean := false;
        CPHA       : boolean := false;
        LSB_FIRST  : boolean := false
    );
end entity;

architecture test of tb_spi_slave is
    function idle_clock return std_logic is
    begin
        if CPOL then
            return '1';
        end if;
        return '0';
    end function;
    constant SAMPLE_ON_RISING : boolean := CPOL = CPHA;
    constant IDLE_LEVEL : std_logic := idle_clock;
    subtype word_t is std_logic_vector(DATA_WIDTH-1 downto 0);
    type words_t is array (natural range <>) of word_t;
    constant WORDS : words_t := (
        std_logic_vector(to_unsigned(165, DATA_WIDTH)),
        std_logic_vector(to_unsigned(60, DATA_WIDTH)),
        std_logic_vector(to_unsigned(150, DATA_WIDTH))
    );
    constant ZERO_WORD : word_t := (others => '0');
    signal rst_n, cs_n : std_logic := '1';
    signal sclk : std_logic := IDLE_LEVEL;
    signal mosi, miso, tx_valid, tx_pop, rx_valid : std_logic;
    signal tx_data, rx_data : word_t;
    signal available : boolean := true;
    signal head : natural range 0 to WORDS'length := 0;
begin
    dut : entity work.spi_slave
        generic map (DATA_WIDTH, CPOL, CPHA, LSB_FIRST)
        port map (rst_n, sclk, cs_n, mosi, miso,
                  tx_data, tx_valid, tx_pop, rx_data, rx_valid);

    -- Model a buffer whose head advances on the same edge as the TX register.
    tx_data <= WORDS(head) when head < WORDS'length else ZERO_WORD;
    tx_valid <= '1' when available and head < WORDS'length else '0';
    buffer_model : process(sclk, cs_n, rst_n)
    begin
        if cs_n = '1' or rst_n = '0' then
            head <= 0;
        elsif (SAMPLE_ON_RISING and falling_edge(sclk)) or
              ((not SAMPLE_ON_RISING) and rising_edge(sclk)) then
            if tx_pop = '1' then
                assert tx_valid = '1' report "Pop from empty buffer" severity failure;
                head <= head + 1;
            end if;
        end if;
    end process;

    stimulus : process
        procedure transfer_word(constant expected : word_t;
                                constant first_word : boolean := false;
                                constant late_arrival : boolean := false) is
            variable index : natural;
            variable initial_valid, expect_pop : boolean;
        begin
            initial_valid := tx_valid = '1';
            for bit_number in 0 to DATA_WIDTH-1 loop
                if LSB_FIRST then
                    index := bit_number;
                else
                    index := DATA_WIDTH-1-bit_number;
                end if;
                mosi <= WORDS(2)(index);
                wait for 5 ns;

                if CPHA then
                    expect_pop := bit_number = 0 and tx_valid = '1';
                    assert (tx_pop = '1') = expect_pop
                        report "Incorrect pop before CPHA=1 TX edge" severity failure;
                    sclk <= not IDLE_LEVEL;
                    wait for 5 ns;
                end if;

                assert miso = expected(index)
                    report "Incorrect MISO at bit " & integer'image(bit_number) severity failure;
                assert (rx_valid = '1') = (bit_number = DATA_WIDTH-1)
                    report "Incorrect RX valid at sampling edge" severity failure;
                if bit_number = DATA_WIDTH-1 then
                    assert rx_data = WORDS(2) report "Incorrect received word" severity failure;
                end if;
                if CPHA then
                    sclk <= IDLE_LEVEL;
                else
                    sclk <= not IDLE_LEVEL;
                end if;
                wait for 5 ns;

                if late_arrival and bit_number = 0 then
                    available <= true;
                    wait for 1 ns;
                end if;

                if not CPHA then
                    if first_word and bit_number = 0 then
                        expect_pop := initial_valid and tx_valid = '1';
                    else
                        expect_pop := bit_number = DATA_WIDTH-1 and tx_valid = '1';
                    end if;
                    assert (tx_pop = '1') = expect_pop
                        report "Incorrect pop before CPHA=0 TX edge" severity failure;
                    sclk <= IDLE_LEVEL;
                    wait for 5 ns;
                end if;
            end loop;
        end procedure;

        procedure deselect is
        begin
            cs_n <= '1';
            wait for 5 ns;
            assert miso = 'Z' and tx_pop = '0' and rx_valid = '0'
                report "Outputs active while deselected" severity failure;
        end procedure;
    begin
        rst_n <= '0';
        wait for 5 ns;
        rst_n <= '1';
        wait for 5 ns;
        cs_n <= '0';
        wait for 5 ns;

        transfer_word(WORDS(0), true);
        transfer_word(WORDS(1));
        transfer_word(WORDS(2));
        transfer_word(ZERO_WORD);
        assert head = WORDS'length report "Incorrect number of consumed words" severity failure;
        deselect;

        -- A word becoming valid after the first sample must wait until the next word.
        available <= false;
        cs_n <= '0';
        wait for 5 ns;
        transfer_word(ZERO_WORD, true, true);
        transfer_word(WORDS(0));
        transfer_word(WORDS(1));
        deselect;

        -- Abort a partial transfer and verify the first-bit bypass restarts.
        cs_n <= '0';
        mosi <= '0';
        wait for 5 ns;
        sclk <= not IDLE_LEVEL;
        wait for 5 ns;
        deselect;
        sclk <= IDLE_LEVEL;
        wait for 5 ns;
        cs_n <= '0';
        wait for 5 ns;
        transfer_word(WORDS(0), true);

        rst_n <= '0';
        wait for 5 ns;
        assert miso = 'Z' and tx_pop = '0' and rx_valid = '0'
            report "Outputs active during reset" severity failure;
        rst_n <= '1';
        wait for 5 ns;
        transfer_word(WORDS(0), true);
        deselect;
        report "SPI PASS" severity note;
        finish;
    end process;
end architecture;
