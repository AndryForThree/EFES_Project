#ifndef ST7789_TRANSPORT_H
#define ST7789_TRANSPORT_H

#include "st7789_config.h"
#include <stddef.h>

/* Internal transport API. The drawing layer owns transaction sequencing. */
HAL_StatusTypeDef ST7789_TransportInit(void);
HAL_StatusTypeDef ST7789_TransportCommand(uint8_t command);
HAL_StatusTypeDef ST7789_TransportData(const uint8_t *data, size_t bytes);
HAL_StatusTypeDef ST7789_TransportBeginPixels(void);
HAL_StatusTypeDef ST7789_TransportStartDMA(const uint8_t *data, uint16_t bytes);
HAL_StatusTypeDef ST7789_TransportPixelsBlocking(const uint8_t *data, uint16_t bytes);
void ST7789_TransportEndPixels(void);
HAL_StatusTypeDef ST7789_TransportGetError(void);
HAL_StatusTypeDef ST7789_TransportClearError(void);

/* Forward the HAL callbacks from main.c. Only the configured SPI is handled. */
void ST7789_TransportTxCompleteISR(SPI_HandleTypeDef *spi);
void ST7789_TransportErrorISR(SPI_HandleTypeDef *spi);

/* Drawing-layer hooks; called only after HAL has finished the SPI transfer. */
void ST7789_PixelsCompleteISR(void);
void ST7789_PixelsErrorISR(void);

#endif
