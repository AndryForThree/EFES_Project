#ifndef __ST7789_H
#define __ST7789_H

#include "fonts.h"
#include "st7789_config.h"

/* Call drawing APIs and Process from main, never from interrupt handlers.
 * BUSY covers the complete drawing operation, including buffer preparation.
 */
typedef enum {
    ST7789_STATE_IDLE,
    ST7789_STATE_BUSY,
    ST7789_STATE_ERROR
} ST7789_State;

typedef enum {
    ST7789_OK,
    ST7789_BUSY,
    ST7789_ERROR,
    ST7789_INVALID_ARGUMENT
} ST7789_Result;

ST7789_State ST7789_GetState(void);
HAL_StatusTypeDef ST7789_GetError(void);
/* Clear a runtime error only when HAL is READY. An initialization failure
 * requires another Init after correcting the configuration. No auto-retry.
 */
ST7789_Result ST7789_ClearError(void);
void ST7789_Process(void);

/**
 *Color of pen
 *If you want to use another color, you can choose one in RGB565 format.
 */

#define WHITE       0xFFFF
#define BLACK       0x0000
#define BLUE        0x001F
#define RED         0xF800
#define MAGENTA     0xF81F
#define GREEN       0x07E0
#define CYAN        0x7FFF
#define YELLOW      0xFFE0
#define GRAY        0X8430
#define BRED        0XF81F
#define GRED        0XFFE0
#define GBLUE       0X07FF
#define BROWN       0XBC40
#define BRRED       0XFC07
#define DARKBLUE    0X01CF
#define LIGHTBLUE   0X7D7C
#define GRAYBLUE    0X5458

#define LIGHTGREEN  0X841F
#define LGRAY       0XC618
#define LGRAYBLUE   0XA651
#define LBBLUE      0X2B12

/* Init and display commands are short blocking operations (Init has delays).
 * ALL drawing APIs are asynchronous: OK accepts one job, BUSY rejects a new
 * request without changing the active job. Call Process regularly until IDLE.
 * Fill/Rectangle endpoints are inclusive; FilledRectangle w/h are pixel counts.
 * Circle jobs clip to the screen; line/triangle endpoints must be on screen.
 */
ST7789_Result ST7789_Init(void);
ST7789_Result ST7789_SetRotation(uint8_t m);
ST7789_Result ST7789_Fill_Color(uint16_t color);
/* Full-screen, symmetric horizontal fade: edge_color -> center_color -> edge_color. */
ST7789_Result ST7789_FillHorizontalGradient(uint16_t edge_color, uint16_t center_color);
ST7789_Result ST7789_DrawPixel(uint16_t x, uint16_t y, uint16_t color);
ST7789_Result ST7789_Fill(uint16_t xSta, uint16_t ySta, uint16_t xEnd, uint16_t yEnd, uint16_t color);
ST7789_Result ST7789_DrawPixel_4px(uint16_t x, uint16_t y, uint16_t color);

ST7789_Result ST7789_DrawLine(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t color);
ST7789_Result ST7789_DrawRectangle(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t color);
ST7789_Result ST7789_DrawCircle(uint16_t x0, uint16_t y0, uint8_t r, uint16_t color);
ST7789_Result ST7789_DrawImage(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *data);
ST7789_Result ST7789_InvertColors(uint8_t invert);

/* Text uses foreground AND background. ASCII 32..126, newline and wrapping.
 * Text, font data and image data must remain valid and unchanged until IDLE.
 * WriteChar copies its character; WriteString retains the caller's pointer.
 * DrawImage preserves the original preformatted SPI byte representation.
 */
ST7789_Result ST7789_WriteChar(uint16_t x, uint16_t y, char ch, FontDef font, uint16_t color, uint16_t bgcolor);
ST7789_Result ST7789_WriteString(uint16_t x, uint16_t y, const char *str, FontDef font, uint16_t color, uint16_t bgcolor);

/* Filled shapes. */
ST7789_Result ST7789_DrawFilledRectangle(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t color);
ST7789_Result ST7789_DrawTriangle(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t x3, uint16_t y3, uint16_t color);
ST7789_Result ST7789_DrawFilledTriangle(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t x3, uint16_t y3, uint16_t color);
ST7789_Result ST7789_DrawFilledCircle(int16_t x0, int16_t y0, int16_t r, uint16_t color);

/* Command functions */
ST7789_Result ST7789_TearEffect(uint8_t tear);

#endif
