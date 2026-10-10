library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity SmartSensorPeripheral_Wrapper is
    port (
        CLK_50M_A : in  std_logic;

        BUTTONS   : in  std_logic_vector(3 downto 0);
        LEDS      : out std_logic_vector(4 downto 0)
    );
end entity SmartSensorPeripheral_Wrapper;

architecture rtl of SmartSensorPeripheral_Wrapper is

    signal leds_internal : std_logic_vector(3 downto 0);

    -- 50 MHz / 25,000,000 = toggle every 0.5 s
    -- Two toggles correspond to one complete 1 Hz period.
    signal counter : unsigned(24 downto 0) := (others => '0');
    signal blink   : std_logic := '1';

begin

    DUT : entity work.SmartSensorPeripheral
        port map (
            buttons_i => BUTTONS,
            leds_o    => leds_internal
        );

    -- Buttons -> LEDs
    LEDS(3 downto 0) <= leds_internal;

    -- Free LED used as clock test
    LEDS(4) <= blink;


    process (CLK_50M_A)
    begin
        if rising_edge(CLK_50M_A) then

            if counter = 24_999_999 then
                counter <= (others => '0');
                blink   <= not blink;
            else
                counter <= counter + 1;
            end if;

        end if;
    end process;

end architecture rtl;