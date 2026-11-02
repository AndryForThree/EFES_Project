#ifndef ST7789_GRAPHICS_H
#define ST7789_GRAPHICS_H

#include "st7789.h"

/* Private bridge between the controller commands and the drawing engine. */
void ST7789_GraphicsReset(void);
void ST7789_GraphicsReady(void);
void ST7789_BeginWindow(uint16_t x0, uint16_t y0,
								uint16_t x1, uint16_t y1);

#endif
