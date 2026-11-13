#ifndef EFES_SPI_H
#define EFES_SPI_H

#include <stddef.h>
#include <stdint.h>
#include "stm32g4xx.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Register-only STM32G431 SPI driver interface (implementation in SPI.c).
 * Scope: master, Motorola SPI, 8-bit frames, software NSS, polling.
 * No HAL/LL dependencies. SPI1, SPI2 and SPI3 are accepted instances.
 *
 * Board code configures the system/APB clocks and GPIO alternate functions
 * before initialization, and controls each slave's CS GPIO around transfers.
 * This driver owns the selected SPI instance exclusively; do not initialize
 * or operate that same instance through CubeMX/HAL code.
 * Calls are synchronous and must not overlap on the same instance.
 */

typedef enum {
    SPI_CLOCK_MODE_0 = 0, /* CPOL = 0, CPHA = 0 */
    SPI_CLOCK_MODE_1,     /* CPOL = 0, CPHA = 1 */
    SPI_CLOCK_MODE_2,     /* CPOL = 1, CPHA = 0 */
    SPI_CLOCK_MODE_3      /* CPOL = 1, CPHA = 1 */
} SPI_clockMode_e;

/* Divider of the selected instance's APB peripheral clock, not the CPU clock. */
typedef enum {
    SPI_PRESCALER_DIV2 = 0,
    SPI_PRESCALER_DIV4,
    SPI_PRESCALER_DIV8,
    SPI_PRESCALER_DIV16,
    SPI_PRESCALER_DIV32,
    SPI_PRESCALER_DIV64,
    SPI_PRESCALER_DIV128,
    SPI_PRESCALER_DIV256
} SPI_prescaler_e;

typedef enum {
    SPI_BIT_ORDER_MSB_FIRST = 0,
    SPI_BIT_ORDER_LSB_FIRST
} SPI_bitOrder_e;

typedef enum {
    SPI_BUS_FULL_DUPLEX = 0, /* Separate MOSI and MISO lines. */
    SPI_BUS_TX_ONLY_1LINE    /* Master drives MOSI; receiver disabled. */
} SPI_busMode_e;

typedef enum {
    SPI_STATUS_OK = 0,
    SPI_STATUS_INVALID_ARGUMENT,
    SPI_STATUS_DISABLED,
    SPI_STATUS_BUSY,
    SPI_STATUS_TIMEOUT,
    SPI_STATUS_HW_ERROR
} SPI_status_e;

typedef struct {
    SPI_clockMode_e clock_mode;
    SPI_prescaler_e prescaler;
    SPI_bitOrder_e bit_order;
    SPI_busMode_e bus_mode;
} SPI_config_t;

/*
 * Enable the instance's RCC clock, reset/configure SPI and leave it enabled.
 * config must be non-NULL. Call only on an unused instance with all CS inactive.
 * Does not configure GPIO, DMA, interrupts or the system/APB clock tree.
 */
SPI_status_e SPI_init(SPI_TypeDef *spi, const SPI_config_t *config);

/*
 * Common transfer contract:
 * - SPI must have been initialized and enabled by SPI_init.
 * - count is a byte count; buffers must contain at least count bytes.
 * - count == 0 is a no-op; buffers may then be NULL.
 * - poll_budget bounds unsuccessful status polls across the WHOLE call,
 *   including the final wait for an empty TX FIFO and BSY = 0.
 *   It is an iteration limit, NOT a duration in milliseconds. Zero permits
 *   no waiting; there is no unlimited-wait sentinel.
 * - OK means the last frame has finished on the bus, so CS may be released.
 * - On timeout/error, a partial transfer may have occurred and SPI may still
 *   be active. The caller must recover the bus before starting another one;
 *   an error return alone does not guarantee that releasing CS is safe.
 */

/* In full duplex, received bytes are drained and discarded to avoid overrun. */
SPI_status_e SPI_transmit(SPI_TypeDef *spi, const uint8_t *tx,
                         size_t count, uint32_t poll_budget);

/* Full duplex only. Send dummy_tx for each byte to generate the receive clock. */
SPI_status_e SPI_receive(SPI_TypeDef *spi, uint8_t *rx, size_t count,
                        uint8_t dummy_tx, uint32_t poll_budget);

/*
 * Full duplex only. Both buffers are required when count > 0.
 * Buffers must be disjoint or exactly identical (in-place exchange).
 */
SPI_status_e SPI_transfer(SPI_TypeDef *spi, const uint8_t *tx, uint8_t *rx,
                         size_t count, uint32_t poll_budget);

/*
 * Wait for transmission to finish, then disable SPI; RCC clock stays enabled.
 * Uses the same poll_budget convention. Already disabled returns OK.
 * On timeout/error, do not force-disable an active transfer.
 * Use SPI_init to configure and enable the instance again.
 */
SPI_status_e SPI_disable(SPI_TypeDef *spi, uint32_t poll_budget);

#ifdef __cplusplus
}
#endif

#endif /* EFES_SPI_H */
