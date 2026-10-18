#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FPGA_DIR=$(cd "$SCRIPT_DIR/../../.." && pwd)
RUN_DIR=$(mktemp -d /tmp/efes-spi-XXXXXX)
echo "SPI simulation logs: $RUN_DIR"
cd "$RUN_DIR"

vlib work
vcom -2008 -work work "$FPGA_DIR/src/spi_slave.vhd" "$FPGA_DIR/tb/TB_spi_slave.vhd" > compile.log 2>&1 || {
    cat compile.log
    exit 1
}

for width in 8 16; do
    for cpol in false true; do
        for cpha in false true; do
            for lsb_first in false true; do
                name="width${width}_cpol${cpol}_cpha${cpha}_lsb${lsb_first}"
                vsim -c -onfinish exit work.tb_spi_slave \
                    -gDATA_WIDTH="$width" -gCPOL="$cpol" -gCPHA="$cpha" -gLSB_FIRST="$lsb_first" \
                    -do 'set BreakOnAssertion 2; run -all; quit -code 1' > "$name.log" 2>&1 || {
                    cat "$name.log"
                    exit 1
                }
                if ! grep -Fq 'SPI PASS' "$name.log"; then
                    cat "$name.log"
                    exit 1
                fi
                echo "PASS $name"
            done
        done
    done
done
