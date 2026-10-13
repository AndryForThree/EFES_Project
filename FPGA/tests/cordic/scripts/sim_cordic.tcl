onerror {quit -code 1}
onbreak {quit -code 1}
set BreakOnAssertion 3

# Prepare the compilation library.
vmap -c
vlib work
vmap work work

# Compile DUT first, then TB. Append their messages to the C compilation log.
set compile_log [open $env(COMPILE_LOG) a]
foreach source [list $env(VHDL_DUT) $env(VHDL_TB)] {
    set failed [catch {exec vcom -2008 -work work $source 2>@1} output]
    puts $output
    puts $compile_log $output
    if {$failed} {
        close $compile_log
        quit -code 1
    }
}
close $compile_log

# Load the TB with the same parameters used by the C model.
set generic_args $env(GENERIC_ARGS)
lappend generic_args "-gINPUT_VECTOR_PATH=\"$env(INPUT_VECTOR)\""
lappend generic_args "-gGOLDEN_OUTPUT_PATH=\"$env(GOLDEN_VECTOR)\""
vsim -voptargs=+acc -wlf waves.wlf {*}$generic_args work.tb_cordic

log -r /tb_cordic/*
run -all

# PASS calls finish in the TB. Returning here without it is a failure.
quit -code 1
