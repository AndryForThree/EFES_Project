library ieee;
use ieee.std_logic_1164.all;

entity SmartSensorPeripheral is
    port (
        buttons_i : in  std_logic_vector(3 downto 0);
        leds_o    : out std_logic_vector(3 downto 0)
    );
end entity SmartSensorPeripheral;

architecture rtl of SmartSensorPeripheral is
begin

    leds_o <= buttons_i;

end architecture rtl;