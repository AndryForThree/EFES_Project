#include "UI_header.h"
#include "UI_private.h"
#include "st7789.h"

#define HEADER_FONT FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define HEADER_TEXT 0xF7DFU
#define HEADER_BORDER 0x21ACU
#define HEADER_BACKGROUND 0x0043U /* Navigation strip, distinct from data cards. */
#define HEADER_ACTIVE 0x3DFFU
#define HEADER_INACTIVE 0x426CU

static struct {
    const char *title;
    uint8_t page, count, step, dot;
} header;

void UI_Header_Reset(const char *title, uint8_t page, uint8_t count)
{
    header.title = title;
    header.page = page;
    header.count = count;
    header.step = header.dot = 0;
}

bool UI_Header_Process(void)
{
    ST7789_Result result = ST7789_OK;
    switch (header.step) {
    case 0:
        result = ST7789_DrawFilledRectangle(0, 0, 320, 22, HEADER_BACKGROUND);
        break;
    case 1:
        result = ST7789_DrawFilledRectangle(0, 21, 320, 1, HEADER_BORDER);
        break;
    case 2:
        result = ST7789_WriteString(8, 3, header.title, HEADER_FONT,
                                    HEADER_TEXT, HEADER_BACKGROUND);
        break;
    case 3:
        result = ST7789_DrawFilledCircle(310 - (header.count - 1 - header.dot) * 10,
                    11, 2, header.dot + 1 == header.page ? HEADER_ACTIVE : HEADER_INACTIVE,
                    HEADER_BACKGROUND);
        if (result == ST7789_OK && ++header.dot == header.count) header.step++;
        return false;
    default:
        return true;
    }
    if (result == ST7789_OK) header.step++;
    return false;
}
