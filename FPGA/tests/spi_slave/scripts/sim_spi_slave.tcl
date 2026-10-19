onerror {quit -code 1}
onbreak {quit -code 1}
set BreakOnAssertion 3

# Prepare the compilation library.
vmap -c
vlib work
vmap work work

# Compile DUT first, then TB, using VHDL-93.
set compile_log [open $env(COMPILE_LOG) a]
foreach source [list $env(VHDL_DUT) $env(VHDL_TB)] {
    set failed [catch {exec vcom -93 -work work $source 2>@1} output]
    puts $output
    puts $compile_log $output
    if {$failed} {
        close $compile_log
        quit -code 1
    }
}
close $compile_log

# Load the TB with the command line parameters.
set generic_args $env(GENERIC_ARGS)
vsim -voptargs=+acc -wlf waves.wlf {*}$generic_args work.tb_spi_slave

log -r /tb_spi_slave/*
run -all

# VHDL-93: the TB ends with wait, so Tcl reads the final result.
if {![string equal -nocase [examine /tb_spi_slave/TB_done] "true"]} {
    puts "SPI TB did not complete"
    quit -code 1
}
if {[string equal -nocase [examine /tb_spi_slave/TB_passed] "true"]} {
    quit -code 0
} else {
    quit -code 1
}
