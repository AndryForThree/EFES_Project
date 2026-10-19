#!/usr/bin/env bash
set -Eeuo pipefail

# Usage: ./sim_spi_slave.bash [-param NAME=VALUE ...]
# Parameters go to Questa as -gTB_NAME=VALUE.

# Paths
readonly SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly FPGA_DIR=$(cd "$SCRIPT_DIR/../../.." && pwd)
readonly TEST_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
readonly RUN_DIR="$TEST_DIR/outputs/sim"
readonly SIM_DIR="$RUN_DIR/questa"

readonly VHDL_DUT="$FPGA_DIR/src/spi_slave.vhd"
readonly VHDL_TB="$FPGA_DIR/tb/TB_spi_slave.vhd"
readonly TCL_SCRIPT="$SCRIPT_DIR/sim_spi_slave.tcl"

readonly LOG_DIR="$RUN_DIR/log"
readonly COMPILE_LOG="$LOG_DIR/compile.log"
readonly VHDL_LOG="$LOG_DIR/vhdl.log"


# Read command line parameters
generic_args=()
while [[ $# -gt 0 ]]; do
    generic_args+=("-gTB_$2")
    shift 2
done

# Prepare the folders where to run the simulation tools.
rm -rf "$RUN_DIR"
mkdir -p "$LOG_DIR" "$SIM_DIR"
cd "$RUN_DIR"
trap 'rm -rf "$SIM_DIR"' EXIT


echo "SPI Slave Simulation flow. Find outputs at: $RUN_DIR"

echo ""
echo "==============================================================="
echo "Running VHDL..."

cd "$SIM_DIR"
export VHDL_DUT VHDL_TB COMPILE_LOG   # The Tcl reads paths and parameters from these environment variables.
export GENERIC_ARGS="${generic_args[*]}"
sim_status=0
vsim -c -onfinish exit -do "do {$TCL_SCRIPT}" > "$VHDL_LOG" 2>&1 || sim_status=$?

# Show the final report and check the simulator exit code.
grep -E "SPI TB (config|report|RESULT):" "$VHDL_LOG" || true
if [[ "$sim_status" -eq 0 ]] && grep -Fq "SPI TB RESULT: PASS" "$VHDL_LOG"; then
    echo "SPI Slave simulation result PASS"
else
    echo "SPI Slave simulation result: FAIL"
    echo "Look logs at: $VHDL_LOG"
    exit 1
fi
