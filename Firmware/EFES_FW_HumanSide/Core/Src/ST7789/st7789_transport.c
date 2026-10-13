#include "st7789_transport.h"

static volatile uint8_t dma_active;
static volatile uint8_t pixels_open;
static volatile HAL_StatusTypeDef transport_error = HAL_ERROR;

static void Select(void)
{
    HAL_GPIO_WritePin(ST7789_CS_PORT, ST7789_CS_PIN, GPIO_PIN_RESET);
}

static void Unselect(void)
{
    HAL_GPIO_WritePin(ST7789_CS_PORT, ST7789_CS_PIN, GPIO_PIN_SET);
}

static HAL_StatusTypeDef RecordError(HAL_StatusTypeDef result)
{
    if (result != HAL_OK) transport_error = result;
    return result;
}

HAL_StatusTypeDef ST7789_TransportInit(void)
{
    if (dma_active || pixels_open) return HAL_BUSY;
    Unselect();
    transport_error = HAL_OK;
    SPI_HandleTypeDef *spi = &ST7789_SPI_PORT;
    /* One explicit configuration: 8-bit SPI, normal byte-wide TX DMA. */
    if (spi->hdmatx == NULL || spi->Init.DataSize != SPI_DATASIZE_8BIT ||
        spi->hdmatx->Init.Direction != DMA_MEMORY_TO_PERIPH ||
        spi->hdmatx->Init.Mode != DMA_NORMAL ||
        spi->hdmatx->Init.MemInc != DMA_MINC_ENABLE ||
        spi->hdmatx->Init.PeriphInc != DMA_PINC_DISABLE ||
        spi->hdmatx->Init.MemDataAlignment != DMA_MDATAALIGN_BYTE ||
        spi->hdmatx->Init.PeriphDataAlignment != DMA_PDATAALIGN_BYTE)
        return RecordError(HAL_ERROR);
    if (HAL_SPI_GetState(spi) != HAL_SPI_STATE_READY)
        return RecordError(HAL_BUSY);
    return HAL_OK;
}

HAL_StatusTypeDef ST7789_TransportCommand(uint8_t command)
{
    if (dma_active || pixels_open) return HAL_BUSY;
    if (transport_error != HAL_OK) return transport_error;
    Select();
    HAL_GPIO_WritePin(ST7789_DC_PORT, ST7789_DC_PIN, GPIO_PIN_RESET);
    HAL_StatusTypeDef result = HAL_SPI_Transmit(&ST7789_SPI_PORT, &command, 1,
                                               ST7789_SPI_TIMEOUT_MS);
    Unselect();
    return RecordError(result);
}

HAL_StatusTypeDef ST7789_TransportData(const uint8_t *data, size_t bytes)
{
    if (dma_active || pixels_open) return HAL_BUSY;
    if (transport_error != HAL_OK) return transport_error;
    if (data == NULL || bytes == 0) return RecordError(HAL_ERROR);
    Select();
    HAL_GPIO_WritePin(ST7789_DC_PORT, ST7789_DC_PIN, GPIO_PIN_SET);
    HAL_StatusTypeDef result = HAL_OK;
    /* Controller parameters only; pixel transfers have their own transaction. */
    while (bytes != 0 && result == HAL_OK) {
        uint16_t chunk = bytes > 65535U ? 65535U : (uint16_t)bytes;
        result = HAL_SPI_Transmit(&ST7789_SPI_PORT, data, chunk,
                                  ST7789_SPI_TIMEOUT_MS);
        data += chunk;
        bytes -= chunk;
    }
    Unselect();
    return RecordError(result);
}

HAL_StatusTypeDef ST7789_TransportBeginPixels(void)
{
    if (dma_active || pixels_open) return HAL_BUSY;
    if (transport_error != HAL_OK) return transport_error;
    pixels_open = 1;
    Select();
    HAL_GPIO_WritePin(ST7789_DC_PORT, ST7789_DC_PIN, GPIO_PIN_SET);
    return HAL_OK;
}

HAL_StatusTypeDef ST7789_TransportStartDMA(const uint8_t *data, uint16_t bytes)
{
    if (dma_active) return HAL_BUSY;
    if (transport_error != HAL_OK) return transport_error;
    if (!pixels_open || data == NULL || bytes == 0 || (bytes & 1U))
        return RecordError(HAL_ERROR);
    /* Set before enabling DMA: a short transfer may complete immediately. */
    dma_active = 1;
    HAL_StatusTypeDef result = HAL_SPI_Transmit_DMA(&ST7789_SPI_PORT, data, bytes);
    if (result != HAL_OK) {
        dma_active = 0;
        RecordError(result);
    }
    return result;
}

void ST7789_TransportEndPixels(void)
{
    if (dma_active) return;
    Unselect();
    pixels_open = 0;
}

HAL_StatusTypeDef ST7789_TransportPixelsBlocking(const uint8_t *data, uint16_t bytes)
{
    if (dma_active) return HAL_BUSY;
    if (transport_error != HAL_OK) return transport_error;
    if (!pixels_open || data == NULL || bytes == 0 || (bytes & 1U))
        return RecordError(HAL_ERROR);
    /* Main-only, short segments: CS is already low and DC is already high. */
    return RecordError(HAL_SPI_Transmit(&ST7789_SPI_PORT, data, bytes,
                                       ST7789_SPI_TIMEOUT_MS));
}

HAL_StatusTypeDef ST7789_TransportGetError(void)
{
    return transport_error;
}

HAL_StatusTypeDef ST7789_TransportClearError(void)
{
    if (dma_active || pixels_open ||
        HAL_SPI_GetState(&ST7789_SPI_PORT) != HAL_SPI_STATE_READY)
        return HAL_BUSY;
    transport_error = HAL_OK;
    return HAL_OK;
}

void ST7789_TransportTxCompleteISR(SPI_HandleTypeDef *spi)
{
    if (spi != &ST7789_SPI_PORT || !dma_active) return;
    /* STM32G4 HAL invokes this after draining SPI and restoring READY. */
    dma_active = 0;
    ST7789_PixelsCompleteISR();
}

void ST7789_TransportErrorISR(SPI_HandleTypeDef *spi)
{
    if (spi != &ST7789_SPI_PORT || !dma_active) return;
    dma_active = 0;
    transport_error = HAL_ERROR;
    ST7789_PixelsErrorISR();
}
