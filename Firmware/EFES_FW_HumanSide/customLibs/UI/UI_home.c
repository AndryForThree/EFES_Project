#include "UI_home.h"
#include "UI_mode.h"
#include "st7789.h"
#include <stdio.h>
#include <string.h>

/* Font choices by role. Sizes/positions below are expressed in pixels. */
#define UI_FONT_CARD_TITLE FONT_BARLOW_SEMI_CONDENSED_BOLD_16
#define UI_FONT_TITLE      FONT_BARLOW_SEMI_CONDENSED_BOLD_16
#define UI_FONT_NUMBER     FONT_RAJDHANI_SEMIBOLD_28
#define UI_FONT_ANGLE      FONT_RAJDHANI_BOLD_42
#define UI_FONT_STATUS     FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define UI_FONT_LABEL      FONT_INTER_MEDIUM_10
#define UI_FONT_DIRECTION  FONT_INTER_MEDIUM_12

#define TEXT_COLOR		0xF7DFU
#define TITLE_COLOR     0x3DFFU /* Saturated sky blue, RGB565. */
#define CARD_SYMBOL_COLOR 0xFE60U /* Warm yellow, RGB565. */
#define MUTED_COLOR		0x8D59U
#define BORDER_COLOR	0x21ACU
#define STATUS_OK_COLOR 0x07D0U
#define STATUS_ERROR_COLOR RED
#define TRACK_COLOR		0x2A4AU
#define UI_WHEEL_ASSET	ASSET_STEERING_WHEEL

#define BAR_CENTER_X				220
#define BAR_SEGMENT_WIDTH			20
#define BAR_SEGMENT_PITCH			22
#define BAR_SEGMENTS_PER_SIDE		4
#define BAR_Y						113
#define BAR_HEIGHT					8
#define BAR_FULL_SCALE				4500 /* +/-450 degrees, expressed in tenths. */

enum {
    HOME_PANELS, HOME_RULE, HOME_DIRECTION_RULE, HOME_LABELS,
    HOME_BAR_TRACK, HOME_BAR_ZERO, HOME_SYMBOLS,
    HOME_STATUS, HOME_WHEEL, HOME_ANGLE, HOME_DIRECTION,
    HOME_BAR_SEGMENTS, HOME_SPEED, HOME_SENSOR_DELTA, HOME_CAN_STATUS,
    HOME_ACTUATOR_STATUS, HOME_STEERING_RATIO,
    HOME_FOOTER, HOME_FINISH
};

static const struct {
    uint16_t x0, y0, x1, y1;
} panels[] = {
    {3, 36, 316, 136},
    {3, 141, 103, 199}, {109, 141, 209, 199}, {215, 141, 316, 199}
};

static const struct {
    uint16_t x, y;
    const char *text;
    FontId font;
    uint16_t width; /* Zero: draw at x. Otherwise center inside this pixel area. */
    uint16_t background, color;
} labels[] = {
    {28, 10, "SENSORS", UI_FONT_STATUS, 0, UI_BACKGROUND, TEXT_COLOR},
    {152, 10, "CAN", UI_FONT_STATUS, 0, UI_BACKGROUND, TEXT_COLOR},
    {252, 10, "ROAD ECU", UI_FONT_STATUS, 0, UI_BACKGROUND, TEXT_COLOR},
    {122, 42, "STEERING REQUEST", UI_FONT_TITLE, 192, UI_CARD_BACKGROUND, TITLE_COLOR},
    {254, 68, "\xB0", UI_FONT_LABEL, 0, UI_CARD_BACKGROUND, MUTED_COLOR},
    {130, 123, "-450", UI_FONT_LABEL, 40, UI_CARD_BACKGROUND, MUTED_COLOR},
    {215, 123, "0", UI_FONT_LABEL, 10, UI_CARD_BACKGROUND, MUTED_COLOR},
    {273, 123, "+450", UI_FONT_LABEL, 40, UI_CARD_BACKGROUND, MUTED_COLOR},
    {32, 147, "SPEED", UI_FONT_CARD_TITLE, 0, UI_CARD_BACKGROUND, TITLE_COLOR},
    {61, 178, "km/h", UI_FONT_LABEL, 0, UI_CARD_BACKGROUND, MUTED_COLOR},
    {138, 147, "DELTA", UI_FONT_CARD_TITLE, 0, UI_CARD_BACKGROUND, TITLE_COLOR},
    {195, 172, "\xB0", UI_FONT_LABEL, 0, UI_CARD_BACKGROUND, MUTED_COLOR},
    {290, 170, ":1", UI_FONT_NUMBER, 0, UI_CARD_BACKGROUND, MUTED_COLOR},
    {244, 147, "MAP", UI_FONT_CARD_TITLE, 0, UI_CARD_BACKGROUND, TITLE_COLOR},
};

/* Static symbols share a 20-pixel box and a four-pixel gap before text. */
static const struct {
    uint16_t x, y;
    GraphicAssetId asset;
    uint16_t background;
} symbols[] = {
    {8, 145, ASSET_SPEED, UI_CARD_BACKGROUND},
    {114, 145, ASSET_SENSOR_DELTA, UI_CARD_BACKGROUND},
    {220, 145, ASSET_STEERING_MAP, UI_CARD_BACKGROUND},
};

static struct {
    UI_State drawn_state;
    uint8_t step;
    uint8_t item;
    bool first_frame;
    /* WriteString retains its pointer: these buffers survive DMA transfers. */
    char number[16];
} home;

/* Pixel-width fields clear old text and center using the actual glyph metrics. */
static ST7789_Result WriteField(uint16_t x, uint16_t y, uint16_t width,
                                FontId font, const char *value, uint16_t color)
{
    return ST7789_WriteTextField(x, y, width, value, font, ST7789_TEXT_CENTER,
                                 color, UI_CARD_BACKGROUND);
}

static int BarSegmentX(unsigned segment)
{
    if (segment < BAR_SEGMENTS_PER_SIDE)
        return BAR_CENTER_X - (BAR_SEGMENTS_PER_SIDE - segment) * BAR_SEGMENT_PITCH;
    return BAR_CENTER_X + 3 + (segment - BAR_SEGMENTS_PER_SIDE) * BAR_SEGMENT_PITCH;
}

static int BarSegmentFill(int angle, unsigned segment)
{
    int magnitude, distance;
    if (segment < BAR_SEGMENTS_PER_SIDE) {
        magnitude = angle < 0 ? -angle : 0;
        distance = BAR_SEGMENTS_PER_SIDE - 1 - segment;
    } else {
        magnitude = angle > 0 ? angle : 0;
        distance = segment - BAR_SEGMENTS_PER_SIDE;
    }
    if (magnitude > BAR_FULL_SCALE) magnitude = BAR_FULL_SCALE;
    int fill = magnitude * BAR_SEGMENTS_PER_SIDE * BAR_SEGMENT_WIDTH / BAR_FULL_SCALE;
    fill -= distance * BAR_SEGMENT_WIDTH;
    if (fill < 0) fill = 0;
    if (fill > BAR_SEGMENT_WIDTH) fill = BAR_SEGMENT_WIDTH;
    return fill;
}

static ST7789_Result UpdateBarSegment(int old_angle, int angle, unsigned segment)
{
    int old_fill = BarSegmentFill(old_angle, segment);
    int new_fill = BarSegmentFill(angle, segment);
    if (old_fill == new_fill) return ST7789_OK;
    int small = old_fill < new_fill ? old_fill : new_fill;
    int large = old_fill > new_fill ? old_fill : new_fill;
    int x = BarSegmentX(segment);
    x += segment < BAR_SEGMENTS_PER_SIDE ? BAR_SEGMENT_WIDTH - large : small;
    return ST7789_DrawFilledRectangle(x, BAR_Y, large - small, BAR_HEIGHT,
                                      new_fill > old_fill ? TITLE_COLOR : TRACK_COLOR);
}

void UI_Home_Reset(void)
{
    home.step = HOME_PANELS;
    home.item = 0;
    home.first_frame = true;
}

bool UI_Home_Process(const UI_State *state)
{
    ST7789_Result result = ST7789_OK;
    const UI_State *old = &home.drawn_state;
    int angle = state->steering_angle_deci_deg;
    uint16_t sensor_delta = UI_SensorDeviation(state);
    bool first = home.first_frame;
    bool mode_changed = first || state->drive_mode != old->drive_mode;

    switch (home.step) {
    case HOME_RULE:
        result = ST7789_DrawFilledRectangle(119, 43, 1, 86, BORDER_COLOR);
        break;
    case HOME_DIRECTION_RULE:
        result = ST7789_DrawFilledRectangle(264, 64, 1, 37, BORDER_COLOR);
        break;
    case HOME_PANELS:
        result = ST7789_DrawRoundedRectangle(panels[home.item].x0, panels[home.item].y0,
                    panels[home.item].x1 - panels[home.item].x0 + 1,
                    panels[home.item].y1 - panels[home.item].y0 + 1,
                    4, BORDER_COLOR, UI_CARD_BACKGROUND, UI_BACKGROUND);
        if (result == ST7789_OK && ++home.item == sizeof(panels) / sizeof(panels[0])) {
            home.item = 0;
            home.step++;
        }
        return false;
    case HOME_LABELS:
        if (labels[home.item].width != 0)
            result = WriteField(labels[home.item].x, labels[home.item].y,
                                labels[home.item].width, labels[home.item].font,
                                labels[home.item].text, labels[home.item].color);
        else
            result = ST7789_WriteString(labels[home.item].x, labels[home.item].y,
                                        labels[home.item].text, labels[home.item].font,
                                        labels[home.item].color,
                                        labels[home.item].background);
        if (result == ST7789_OK && ++home.item == sizeof(labels) / sizeof(labels[0])) {
            home.item = 0;
            home.step++;
        }
        return false;
    case HOME_BAR_TRACK:
        result = ST7789_DrawFilledRectangle(BarSegmentX(home.item), BAR_Y,
                                            BAR_SEGMENT_WIDTH, BAR_HEIGHT, TRACK_COLOR);
        if (result == ST7789_OK && ++home.item == 2 * BAR_SEGMENTS_PER_SIDE) {
            home.item = 0;
            home.step++;
        }
        return false;
    case HOME_BAR_ZERO:
        result = ST7789_DrawFilledRectangle(BAR_CENTER_X, BAR_Y - 2, 1,
                                            BAR_HEIGHT + 4, TEXT_COLOR);
        break;
    case HOME_FOOTER:
        if (mode_changed && !UI_Mode_Process(state->drive_mode)) return false;
        break;
    case HOME_STATUS:
        if (first || state->sensors_valid != old->sensors_valid)
            result = ST7789_DrawSymbol(6, 10,
                            state->sensors_valid ? ASSET_TICK : ASSET_CROSS,
                            state->sensors_valid ? STATUS_OK_COLOR : STATUS_ERROR_COLOR,
                            UI_BACKGROUND);
        break;
    case HOME_SYMBOLS:
        result = ST7789_DrawSymbol(symbols[home.item].x, symbols[home.item].y,
                                   symbols[home.item].asset, CARD_SYMBOL_COLOR,
                                   symbols[home.item].background);
        if (result == ST7789_OK && ++home.item == sizeof(symbols) / sizeof(symbols[0])) {
            home.item = 0;
            home.step++;
        }
        return false;
    case HOME_WHEEL:
        /* One-degree visual resolution avoids retransmitting identical poses. */
        if (first || angle / 10 != old->steering_angle_deci_deg / 10)
            result = ST7789_DrawAsset(18, 47, UI_WHEEL_ASSET,
                                      (angle / 10) * 10, UI_CARD_BACKGROUND);
        break;
    case HOME_ANGLE:
        if (first || angle != old->steering_angle_deci_deg) {
            int magnitude = angle < 0 ? -angle : angle;
            snprintf(home.number, sizeof(home.number), "%c%d.%d",
                     angle < 0 ? '-' : '+', magnitude / 10, magnitude % 10);
            result = ST7789_WriteNumberField(121, 68, 132, home.number,
                                               UI_FONT_ANGLE, TEXT_COLOR, UI_CARD_BACKGROUND);
        }
        break;
    case HOME_DIRECTION:
        if (first || (angle > 0) != (old->steering_angle_deci_deg > 0) ||
            (angle < 0) != (old->steering_angle_deci_deg < 0))
            result = ST7789_WriteTextField(269, 86, 47,
                                angle > 0 ? "RIGHT" : (angle < 0 ? "LEFT" : "ZERO"),
                                UI_FONT_DIRECTION, ST7789_TEXT_LEFT,
                                TITLE_COLOR, UI_CARD_BACKGROUND);
        break;
    case HOME_BAR_SEGMENTS:
        result = UpdateBarSegment(first ? 0 : old->steering_angle_deci_deg, angle, home.item);
        if (result == ST7789_OK && ++home.item == 2 * BAR_SEGMENTS_PER_SIDE) {
            home.item = 0;
            home.step++;
        }
        return false;
    case HOME_SPEED:
        if (first || state->vehicle_speed_kmh != old->vehicle_speed_kmh) {
            snprintf(home.number, sizeof(home.number), "%u", (unsigned)state->vehicle_speed_kmh);
            result = ST7789_WriteNumberField(9, 170, 48, home.number,
                                               UI_FONT_NUMBER, TEXT_COLOR, UI_CARD_BACKGROUND);
        }
        break;
    case HOME_SENSOR_DELTA:
        if (first || sensor_delta != UI_SensorDeviation(old) ||
            state->sensors_valid != old->sensors_valid) {
            if (state->sensors_valid)
                snprintf(home.number, sizeof(home.number), "%u.%u",
                         (unsigned)sensor_delta / 10U,
                         (unsigned)sensor_delta % 10U);
            else
                strcpy(home.number, "--.-");
            result = ST7789_WriteNumberField(130, 170, 64, home.number,
                                               UI_FONT_NUMBER, TEXT_COLOR, UI_CARD_BACKGROUND);
        }
        break;
    case HOME_CAN_STATUS:
        if (first || state->can_online != old->can_online)
            result = ST7789_DrawSymbol(130, 10,
                            state->can_online ? ASSET_TICK : ASSET_CROSS,
                            state->can_online ? STATUS_OK_COLOR : STATUS_ERROR_COLOR,
                            UI_BACKGROUND);
        break;
    case HOME_ACTUATOR_STATUS:
        if (first || state->actuator_ready != old->actuator_ready)
            result = ST7789_DrawSymbol(230, 10,
                            state->actuator_ready ? ASSET_TICK : ASSET_CROSS,
                            state->actuator_ready ? STATUS_OK_COLOR : STATUS_ERROR_COLOR,
                            UI_BACKGROUND);
        break;
    case HOME_STEERING_RATIO:
        if (first || state->steering_ratio_deci != old->steering_ratio_deci) {
            snprintf(home.number, sizeof(home.number), "%u.%u",
                     (unsigned)state->steering_ratio_deci / 10U,
                     (unsigned)state->steering_ratio_deci % 10U);
            result = ST7789_WriteNumberField(218, 170, 72, home.number,
                                               UI_FONT_NUMBER, TEXT_COLOR, UI_CARD_BACKGROUND);
        }
        break;
    case HOME_FINISH:
        home.drawn_state = *state;
        home.first_frame = false;
        home.step = HOME_STATUS;
        return true;
    }

    if (result == ST7789_OK) home.step++;
    return false;
}
