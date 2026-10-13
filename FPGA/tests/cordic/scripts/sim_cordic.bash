#!/usr/bin/env bash
set -Eeuo pipefail

# Usage: ./sim_cordic.bash [-param NAME=VALUE ...]
# Parameters go to C as NAME=VALUE and to Questa as -gTB_NAME=VALUE.

# Paths
readonly SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly FPGA_DIR=$(cd "$SCRIPT_DIR/../../.." && pwd)
readonly TEST_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
readonly C_SOURCE_DIR="$TEST_DIR/model"
readonly RUN_DIR="$TEST_DIR/outputs/sim"
readonly SIM_DIR="$RUN_DIR/questa"

readonly C_MAIN="$C_SOURCE_DIR/main_sim.c"
readonly C_MODEL="$C_SOURCE_DIR/cordic.c"
readonly VHDL_DUT="$FPGA_DIR/src/cordic.vhd"
readonly VHDL_TB="$FPGA_DIR/tb/TB_cordic.vhd"
readonly TCL_SCRIPT="$SCRIPT_DIR/sim_cordic.tcl"

readonly EXECUTABLE="$RUN_DIR/executable/main_sim"
readonly INPUT_VECTOR="$RUN_DIR/vectors/input_vectors.txt"
readonly GOLDEN_VECTOR="$RUN_DIR/vectors/golden_outputs.txt"
readonly LOG_DIR="$RUN_DIR/log"
readonly COMPILE_LOG="$LOG_DIR/compile.log"
readonly MAIN_SIM_LOG="$LOG_DIR/main_sim.log"
readonly VHDL_LOG="$LOG_DIR/vhdl.log"


# Read command line parameters
params=()
generic_args=()
while [[ $# -gt 0 ]]; do
    params+=("$2")
    generic_args+=("-gTB_$2")
    shift 2
done

# Prepare the folders where to run the simulation tools and programs
rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR/executable" 
mkdir "$RUN_DIR/vectors" "$LOG_DIR" "$SIM_DIR"
cd "$RUN_DIR"
trap 'rm -rf "$SIM_DIR"' EXIT


echo "CORDIC Simulation flow. Find outputs at: $RUN_DIR"

# Compile the Golden Model
echo ""
echo "==============================================================="
echo "Compiling C..."
if ! gcc -std=c11 -Wall -Wextra -O0 \
    "$C_MAIN" "$C_MODEL" \
    -lm -o "$EXECUTABLE" > "$COMPILE_LOG" 2>&1; then
    echo "CORDIC FAIL"
    echo "Look logs at: $COMPILE_LOG"
    exit 1
fi

# Execute the C program for simulation. Generate the input vector and execute the
# Golden Model on it
echo ""
echo "==============================================================="
echo "Running C..."
if ! "$EXECUTABLE" "${params[@]}" 2>&1 | tee "$MAIN_SIM_LOG"; then
    echo "CORDIC FAIL"
    echo "Look logs at: $MAIN_SIM_LOG"
    exit 1
fi




echo ""
echo "==============================================================="
echo "Running VHDL..."

cd "$SIM_DIR"
export VHDL_DUT VHDL_TB INPUT_VECTOR GOLDEN_VECTOR COMPILE_LOG	# The Tcl reads paths and parameters from these environment variables.
export GENERIC_ARGS="${generic_args[*]}"
vsim -c -onfinish exit -do "do {$TCL_SCRIPT}" > "$VHDL_LOG" 2>&1 || true

# The result is determined by the TB report in the VHDL log.
if grep -Fq "PASS" "$VHDL_LOG"; then
    echo "CORDIC simulation result PASS"
else
    echo "CORDIC simulation result: FAIL"
    echo "Look logs at: $VHDL_LOG"
    exit 1
fi
