#include "UI_mode.h"
#include "UI_private.h"
#include "st7789.h"

#define MODE_TEXT_COLOR 0xF7DFU
#define MODE_RULE_COLOR 0x8D59U

static const struct {
    const char *text;
    uint16_t color;
} modes[] = {
    [UI_DRIVE_NORMAL] = {"COMFORT", 0x3934U},
    [UI_DRIVE_ECO] = {"ECO", 0x032CU},
    [UI_DRIVE_SPORT] = {"SPORT", 0xB984U}
};

static uint8_t step;
static uint16_t symbol_x, text_x;

void UI_Mode_Reset(void)
{
    step = 0;
}

bool UI_Mode_Process(UI_DriveMode mode)
{
    ST7789_Result result = ST7789_OK;
    uint16_t color = modes[mode].color;
    switch (step) {
    case 0: {
        ST7789_TextSize size;
        ST7789_MeasureText(modes[mode].text, UI_FONT_MODE, &size);
        uint16_t icon_width = Assets[ASSET_DRIVE_MODE].width;
        symbol_x = (320 - icon_width - 17 - size.width) / 2;
        text_x = symbol_x + icon_width + 17;
        result = ST7789_DrawRoundedRectangle(3, 205, 314, 31, 5,
                                             color, color, UI_BACKGROUND);
        break;
    }
    case 1:
        result = ST7789_DrawAsset(symbol_x, 208, ASSET_DRIVE_MODE, 0, color);
        break;
    case 2:
        result = ST7789_DrawFilledRectangle(text_x - 9, 210, 1, 21, MODE_RULE_COLOR);
        break;
    case 3:
        result = ST7789_WriteString(text_x, 208, modes[mode].text, UI_FONT_MODE,
                                    MODE_TEXT_COLOR, color);
        break;
    default:
        step = 0;
        return true;
    }
    if (result == ST7789_OK) step++;
    return false;
}
