#ifndef __ST7789_H
#define __ST7789_H

#include "Fonts/fonts_generated.h"
#include "Assets/assets_generated.h"
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
/* Antialiased circles redraw their clipped square on a uniform background.
 * DrawCircle also clears the interior to background. */
ST7789_Result ST7789_DrawCircle(uint16_t x0, uint16_t y0, uint8_t r, uint16_t color, uint16_t background);
ST7789_Result ST7789_DrawImage(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *data);
ST7789_Result ST7789_InvertColors(uint8_t invert);

typedef enum {
    ST7789_TEXT_LEFT,
    ST7789_TEXT_CENTER,
    ST7789_TEXT_RIGHT
} ST7789_TextAlign;

typedef struct {
    uint32_t width;
    uint32_t height;
} ST7789_TextSize;

/* Antialiased text: 4-bit coverage blended with bgcolor, proportional metrics,
 * integer advances, no kerning. Single-byte characters,
 * not UTF-8. Unsupported characters return INVALID_ARGUMENT.
 * MeasureText measures explicit lines, without screen wrapping.
 * WriteString wraps at the right screen edge; newline starts at x=0.
 * Text, font data and image data must remain valid and unchanged until IDLE.
 * WriteChar copies its character; WriteString retains the caller's pointer.
 * DrawImage preserves the original preformatted SPI byte representation.
 */
ST7789_Result ST7789_WriteChar(uint16_t x, uint16_t y, char ch, FontId font, uint16_t color, uint16_t bgcolor);
ST7789_Result ST7789_WriteString(uint16_t x, uint16_t y, const char *str, FontId font, uint16_t color, uint16_t bgcolor);
ST7789_Result ST7789_MeasureText(const char *str, FontId font, ST7789_TextSize *size);
/* Single line in a fixed pixel-width area; clears the whole area, including
 * old text. Returns INVALID_ARGUMENT if the text does not fit. No truncation.
 * Height is Fonts[font].height. Empty text clears the area.
 */
ST7789_Result ST7789_WriteTextField(uint16_t x, uint16_t y, uint16_t width,
    const char *str, FontId font, ST7789_TextAlign align, uint16_t color, uint16_t bgcolor);
/* Numeric field: 0..9, + and - use equal-width slots; dot uses a narrower slot.
 * Always right-aligned in the pixel area. Clears the whole area on each draw.
 * Keep decimal precision constant in the caller to keep the decimal point fixed.
 * No parsing/formatting: only digits, +, - and . are accepted (or empty text).
 */
ST7789_Result ST7789_WriteNumberField(uint16_t x, uint16_t y, uint16_t width,
    const char *number, FontId font, uint16_t color, uint16_t bgcolor);

/* Antialiased opaque rounded panel: border is one pixel; outside corners use background.
 * Use border == fill for a solid rounded rectangle. Entire panel must fit.
 */
ST7789_Result ST7789_DrawRoundedRectangle(uint16_t x, uint16_t y, uint16_t w,
    uint16_t h, uint16_t radius, uint16_t border, uint16_t fill, uint16_t background);

/* Rounded antialiased track and fill in one window; filled is a pixel width,
 * clamped to w. Requires w >= h >= 2, on a uniform background. */
ST7789_Result ST7789_DrawProgressBar(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
    uint16_t filled, uint16_t color, uint16_t track, uint16_t background);

typedef struct {
    int16_t a, b;
} ST7789_GraphSample;

typedef struct {
    uint16_t x, y, width, height;
    int16_t minimum, maximum;
    uint16_t color_a, color_b, grid, background;
    uint8_t series_count; /* 1 or 2. */
} ST7789_Graph;

/* One sample per column, oldest first, newest at the right edge. Count <= width.
 * Draws background, dashed grid and the selected series in one DMA window.
 * Descriptor and samples must remain unchanged until IDLE. Values are clamped
 * to the shared Y scale. Count zero draws only the grid; no framebuffer.
 */
ST7789_Result ST7789_DrawGraph(const ST7789_Graph *graph,
    const ST7789_GraphSample *samples, uint16_t count);

/* Filled shapes. */
ST7789_Result ST7789_DrawFilledRectangle(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t color);
ST7789_Result ST7789_DrawTriangle(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t x3, uint16_t y3, uint16_t color);
ST7789_Result ST7789_DrawFilledTriangle(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t x3, uint16_t y3, uint16_t color);
ST7789_Result ST7789_DrawFilledCircle(int16_t x0, int16_t y0, int16_t r, uint16_t color, uint16_t background);

/* Stylized three-spoke wheel in one square window, including its background.
 * Positive angles rotate clockwise. angle_deci_deg is in tenths of a degree.
 * The entire square must fit on screen; diameter must be at least 16 pixels.
 */
ST7789_Result ST7789_DrawSteeringWheel(uint16_t x, uint16_t y, uint16_t diameter,
                                      int16_t angle_deci_deg, uint16_t color,
                                      uint16_t accent, uint16_t background);

/* Indexed asset, rotated clockwise in tenths of a degree. One fixed square
 * canvas of side max(asset.width, asset.height), top-left at x,y. No scaling.
 * 4-bit palette index + 4-bit alpha per pixel, blended with background.
 * Bilinear RGB565 filtering during rotation; outside samples use background.
 * No display readback or additional framebuffer.
 * Keep the artwork inside its canvas at all angles to avoid clipped corners.
 */
ST7789_Result ST7789_DrawAsset(uint16_t x, uint16_t y, GraphicAssetId asset,
                              int16_t angle_deci_deg, uint16_t background);

/* Monochrome asset: use its alpha with a caller-selected RGB565 color. */
ST7789_Result ST7789_DrawSymbol(uint16_t x, uint16_t y, GraphicAssetId asset,
                               uint16_t color, uint16_t background);

/* Command functions */
ST7789_Result ST7789_TearEffect(uint8_t tear);

#endif
