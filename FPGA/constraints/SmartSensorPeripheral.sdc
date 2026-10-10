#============================================================
# Primary board clock
#============================================================
# On-board 50 MHz oscillator
# Period = 1 / 50 MHz = 20 ns

create_clock -name CLK_50M -period 20.000 [get_ports {CLK_50M_A}]