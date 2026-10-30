#ifndef ST7789_CONFIG_H
#define ST7789_CONFIG_H

#include "main.h"

/* CubeMX owns SCK/MOSI and the DMA configuration of this SPI handle. */
#define ST7789_SPI_PORT hspi1
extern SPI_HandleTypeDef ST7789_SPI_PORT;

#define ST7789_CS_PORT SPI1_CS_GPIO_Port
#define ST7789_CS_PIN  SPI1_CS_Pin
#define ST7789_DC_PORT Display_DC_GPIO_Port
#define ST7789_DC_PIN  Display_DC_Pin

/* Full 240x320 panel, used in landscape. Rotation 1 or 3 is supported. */
#define ST7789_WIDTH  320U
#define ST7789_HEIGHT 240U
#define ST7789_ROTATION 3U
#define ST7789_DEFAULT_INVERSION 0U

/* Two software buffers, each containing this many RGB565 pixels.
 * Pixel storage = 2 * 2 * ST7789_BUFFER_PIXELS (1280 bytes by default),
 * plus a few bytes of buffer metadata and drawing state.
 * Process prepares at most one buffer per call. Larger buffers cost more
 * RAM and more CPU time per call, but require fewer DMA launches.
 */
#define ST7789_BUFFER_PIXELS 320U

/* Owned copy of the active text, including its terminating null byte. */
#define ST7789_TEXT_BUFFER_SIZE	256U

#if ST7789_TEXT_BUFFER_SIZE < 2
#error ST7789_TEXT_BUFFER_SIZE must be at least 2
#endif
/* A complete window of at most this many pixels uses blocking SPI in Process.
 * The whole drawing job remains asynchronous. No blocking pixel sends in ISR.
 */
#define ST7789_BLOCKING_MAX_PIXELS 8U
#define ST7789_SPI_TIMEOUT_MS 100U

#if (ST7789_BUFFER_PIXELS < 1) || (ST7789_BUFFER_PIXELS > 32767)
#error ST7789_BUFFER_PIXELS must be between 1 and 32767
#endif

/* RESET is physically wired to MCU nRST; no software GPIO reset. */
#endif
