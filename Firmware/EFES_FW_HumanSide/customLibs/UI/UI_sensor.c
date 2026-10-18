#include "UI_sensor.h"
#include "UI_history.h"
#include "st7789.h"
#include <stdio.h>

#define SENSOR_FONT_TITLE FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define SENSOR_FONT_ANGLE FONT_RAJDHANI_BOLD_40
#define SENSOR_FONT_VALUE FONT_RAJDHANI_BOLD_42
#define SENSOR_FONT_NA FONT_RAJDHANI_BOLD_28
#define SENSOR_FONT_HISTORY FONT_BARLOW_SEMI_CONDENSED_BOLD_12
#define SENSOR_FONT_UPDATE FONT_BARLOW_SEMI_CONDENSED_BOLD_10
#define SENSOR_FONT_AXIS FONT_INTER_MEDIUM_10
#define SENSOR_FONT_LEGEND FONT_BARLOW_SEMI_CONDENSED_BOLD_10
#define SENSOR_FONT_UNIT FONT_INTER_MEDIUM_10

#define SENSOR_TEXT 0xF7DFU
#define SENSOR_TITLE 0x3DFFU
#define SENSOR_BORDER 0x21ACU
#define SENSOR_NORMAL 0x07D0U
#define SENSOR_FAULT RED
#define SENSOR_STALE 0xFE60U
#define SENSOR_TRACK 0x2A4AU
#define DEVIATION_BAR_X 12
#define DEVIATION_BAR_Y 114
#define DEVIATION_BAR_WIDTH 156
#define DEVIATION_BAR_HEIGHT 8
#define GRAPH_X 41U
#define GRAPH_Y 162U
#define GRAPH_HEIGHT_PX 46U
#define GRAPH_COLOR 0x06D8U

static ST7789_Graph graph = {
    .x = GRAPH_X, .y = GRAPH_Y, .width = GRAPH_WIDTH_PX, .height = GRAPH_HEIGHT_PX,
    .minimum = 0,
    .color_a = GRAPH_COLOR,
    .grid = SENSOR_BORDER, .background = UI_CARD_BACKGROUND,
    .series_count = 1
};
/* The history ring continues changing; this copy belongs to the active draw. */
static ST7789_GraphSample graph_snapshot[GRAPH_SAMPLES];

enum {
    SENSOR_PANELS, SENSOR_LABELS, SENSOR_GRAPH_LEGEND,
    SENSOR_CHANNEL_A, SENSOR_CHANNEL_B,
    SENSOR_DEVIATION_VALUE, SENSOR_DEVIATION_NA, SENSOR_DEVIATION_UNIT, SENSOR_DEVIATION_BAR,
    SENSOR_HISTORY_DOT, SENSOR_HISTORY_TEXT, SENSOR_GRAPH_AXES, SENSOR_GRAPH,
    SENSOR_FINISH
};

static const struct {
    uint16_t x, y, width, height;
} panels[] = {
    {3, 26, 154, 56}, {163, 26, 154, 56},
    {3, 87, 314, 42}, {3, 134, 314, 102}
};

static const struct {
    uint16_t x, y;
    const char *text;
    FontId font;
} labels[] = {
    {12, 31, "CHANNEL A", SENSOR_FONT_TITLE},
    {172, 31, "CHANNEL B", SENSOR_FONT_TITLE},
    {141, 47, "\xB0", SENSOR_FONT_UNIT},
    {301, 47, "\xB0", SENSOR_FONT_UNIT},
    {12, 93, "CHANNEL DEVIATION", SENSOR_FONT_TITLE},
    {12, 140, "DEVIATION HISTORY", SENSOR_FONT_TITLE},
    {148, 142, "LAST UPDATE:", SENSOR_FONT_UPDATE},
    {137, 221, "DEVIATION", SENSOR_FONT_LEGEND},
};

static struct {
    UI_State drawn_state;
    uint8_t step, item;
    bool first_frame;
    bool stale;
    uint16_t drawn_color, drawn_fill;
    uint8_t drawn_history;
    uint32_t graph_updated_at, graph_version;
    uint16_t drawn_graph_limit;
    char axis_text[6][16];
    char number[16]; /* Retained by the driver until the drawing is complete. */
} sensor;

static int BarFill(const UI_State *state)
{
    /* Fault is a hardware verdict. Numeric saturation alone never changes color. */
    if (!state->channel_a_valid || !state->channel_b_valid ||
        state->sensor_plausibility_fault) return DEVIATION_BAR_WIDTH;
    uint32_t fill = (uint32_t)UI_SensorDeviation(state) * DEVIATION_BAR_WIDTH /
                    state->sensor_deviation_limit_deci_deg;
    return fill > DEVIATION_BAR_WIDTH ? DEVIATION_BAR_WIDTH : (int)fill;
}

static ST7789_Result WriteAngle(uint16_t x, int angle)
{
    int magnitude = angle < 0 ? -angle : angle;
    snprintf(sensor.number, sizeof(sensor.number), "%c%d.%d",
             angle < 0 ? '-' : '+', magnitude / 10, magnitude % 10);
    return ST7789_WriteNumberField(x, 47, 132, sensor.number,
                                   SENSOR_FONT_ANGLE, SENSOR_TEXT, UI_CARD_BACKGROUND);
}

static void FormatGraphTime(char *text, uint32_t ms)
{
    if (ms == 0) snprintf(text, 16, "0s");
    else if (ms % 1000U == 0) snprintf(text, 16, "-%lus", (unsigned long)(ms / 1000U));
    else snprintf(text, 16, "-%lu.%lus", (unsigned long)(ms / 1000U),
                  (unsigned long)((ms % 1000U) / 100U));
}

void UI_Sensor_Reset(void)
{
    sensor.step = SENSOR_PANELS;
    sensor.item = 0;
    sensor.first_frame = true;
    FormatGraphTime(sensor.axis_text[3], GRAPH_HISTORY_MS);
    FormatGraphTime(sensor.axis_text[4], GRAPH_HISTORY_MS / 2U);
    FormatGraphTime(sensor.axis_text[5], 0);
}

bool UI_Sensor_Process(const UI_State *state)
{
    ST7789_Result result = ST7789_OK;
    const UI_State *old = &sensor.drawn_state;
    bool first = sensor.first_frame;
    uint16_t deviation = UI_SensorDeviation(state);
    /* Capture age once per refresh: one coherent color/status across all jobs. */
    if (sensor.step == SENSOR_CHANNEL_A) {
        sensor.stale = UI_SensorStale(state, HAL_GetTick());
        uint32_t maximum = (uint32_t)state->sensor_deviation_limit_deci_deg * GRAPH_DEVIATION_SCALE;
        graph.maximum = maximum > INT16_MAX ? INT16_MAX : (int16_t)maximum;
    }
    bool scale_changed = first || state->sensor_deviation_limit_deci_deg != sensor.drawn_graph_limit;
    bool invalid = !state->channel_a_valid || !state->channel_b_valid;
    bool old_invalid = !old->channel_a_valid || !old->channel_b_valid;
    uint16_t color = invalid || state->sensor_plausibility_fault ? SENSOR_FAULT :
                     (sensor.stale ? SENSOR_STALE : SENSOR_NORMAL);
    bool history_fault = invalid || state->sensor_plausibility_fault;
    uint8_t history = history_fault ? 2 : (sensor.stale ? 1 : 0);
    uint16_t history_color = history_fault ? SENSOR_FAULT : (sensor.stale ? SENSOR_STALE : SENSOR_NORMAL);
    uint16_t fill = BarFill(state);
    bool value_changed = first || invalid != old_invalid ||
                         (!invalid && deviation != UI_SensorDeviation(old)) || color != sensor.drawn_color;

    switch (sensor.step) {
    case SENSOR_PANELS:
        result = ST7789_DrawRoundedRectangle(panels[sensor.item].x, panels[sensor.item].y,
                    panels[sensor.item].width, panels[sensor.item].height, 4,
                    SENSOR_BORDER, UI_CARD_BACKGROUND, UI_BACKGROUND);
        if (result == ST7789_OK && ++sensor.item == sizeof(panels) / sizeof(panels[0])) {
            sensor.item = 0;
            sensor.step++;
        }
        return false;
    case SENSOR_LABELS:
        result = ST7789_WriteString(labels[sensor.item].x, labels[sensor.item].y,
                    labels[sensor.item].text, labels[sensor.item].font,
                    SENSOR_TITLE, UI_CARD_BACKGROUND);
        if (result == ST7789_OK && ++sensor.item == sizeof(labels) / sizeof(labels[0])) {
            sensor.item = 0;
            sensor.step++;
        }
        return false;
    case SENSOR_GRAPH_AXES:
        if (!scale_changed) {
            sensor.step++;
            return false;
        }
        if (sensor.item < 3) {
            unsigned value = graph.maximum * (2U - sensor.item) / 2U;
            snprintf(sensor.axis_text[sensor.item], 16, "%u.%u\xB0", value / 10U, value % 10U);
            uint16_t y = GRAPH_Y + sensor.item * (GRAPH_HEIGHT_PX - 1U) / 2U - 6;
            result = ST7789_WriteTextField(7, y, 32, sensor.axis_text[sensor.item],
                        SENSOR_FONT_AXIS, ST7789_TEXT_RIGHT, SENSOR_TITLE, UI_CARD_BACKGROUND);
        } else {
            unsigned tick = sensor.item - 3;
            uint16_t x = tick == 0 ? GRAPH_X :
                         (tick == 1 ? GRAPH_X + (GRAPH_WIDTH_PX - 1U) / 2U - 20 :
                                      GRAPH_X + GRAPH_WIDTH_PX - 40);
            ST7789_TextAlign align = tick == 0 ? ST7789_TEXT_LEFT :
                                      (tick == 1 ? ST7789_TEXT_CENTER : ST7789_TEXT_RIGHT);
            result = ST7789_WriteTextField(x, 209, 40, sensor.axis_text[sensor.item],
                        SENSOR_FONT_AXIS, align, SENSOR_TITLE, UI_CARD_BACKGROUND);
        }
        if (result == ST7789_OK && ++sensor.item == 6) {
            sensor.item = 0;
            sensor.step++;
        }
        return false;
    case SENSOR_GRAPH_LEGEND:
        result = ST7789_DrawFilledRectangle(119, 227, 13, 2, GRAPH_COLOR);
        break;
    case SENSOR_CHANNEL_A:
        if (first || state->channel_a_angle_deci_deg != old->channel_a_angle_deci_deg)
            result = WriteAngle(8, state->channel_a_angle_deci_deg);
        break;
    case SENSOR_CHANNEL_B:
        if (first || state->channel_b_angle_deci_deg != old->channel_b_angle_deci_deg)
            result = WriteAngle(168, state->channel_b_angle_deci_deg);
        break;
    case SENSOR_DEVIATION_VALUE:
        if (value_changed) {
            if (invalid) sensor.number[0] = '\0';
            else snprintf(sensor.number, sizeof(sensor.number), "%u.%u",
                          (unsigned)deviation / 10U, (unsigned)deviation % 10U);
            /* Empty numeric field clears the entire digit height before N/A. */
            result = ST7789_WriteNumberField(178, 91, 120, sensor.number,
                        SENSOR_FONT_VALUE, color, UI_CARD_BACKGROUND);
        }
        break;
    case SENSOR_DEVIATION_NA:
        if (invalid && value_changed)
            result = ST7789_WriteTextField(178, 94, 120, "N/A", SENSOR_FONT_NA,
                        ST7789_TEXT_RIGHT, SENSOR_FAULT, UI_CARD_BACKGROUND);
        break;
    case SENSOR_DEVIATION_UNIT:
        if (first || invalid != old_invalid || color != sensor.drawn_color)
            result = ST7789_WriteTextField(300, 91, 10, invalid ? "" : "\xB0",
                        SENSOR_FONT_UNIT, ST7789_TEXT_LEFT, color, UI_CARD_BACKGROUND);
        break;
    case SENSOR_DEVIATION_BAR:
        if (first || fill != sensor.drawn_fill || color != sensor.drawn_color)
            result = ST7789_DrawProgressBar(DEVIATION_BAR_X, DEVIATION_BAR_Y,
                        DEVIATION_BAR_WIDTH, DEVIATION_BAR_HEIGHT, fill,
                        color, SENSOR_TRACK, UI_CARD_BACKGROUND);
        break;
    case SENSOR_HISTORY_DOT:
        if (first || history != sensor.drawn_history)
            result = ST7789_DrawFilledCircle(214, 148, 3, history_color, UI_CARD_BACKGROUND);
        break;
    case SENSOR_HISTORY_TEXT:
        if (first || history != sensor.drawn_history)
            result = ST7789_WriteTextField(224, 141, 83,
                        history_fault ? "FAULT" : (sensor.stale ? "STALE - >1s ago" : "LIVE - <1s ago"),
                        SENSOR_FONT_HISTORY, ST7789_TEXT_RIGHT, history_color, UI_CARD_BACKGROUND);
        break;
    case SENSOR_GRAPH: {
        uint32_t now = HAL_GetTick();
        uint32_t version = UI_History_Version();
        if (scale_changed || (version != sensor.graph_version &&
            (uint32_t)(now - sensor.graph_updated_at) >= GRAPH_REFRESH_MS)) {
            uint16_t count = UI_History_Copy(graph_snapshot);
            for (uint16_t i = 0; i < count; i++) {
                int32_t difference = (int32_t)graph_snapshot[i].a - graph_snapshot[i].b;
                uint32_t value = difference < 0 ? -difference : difference;
                graph_snapshot[i].a = value > (uint32_t)graph.maximum ? graph.maximum : (int16_t)value;
            }
            result = ST7789_DrawGraph(&graph, graph_snapshot, count);
            if (result == ST7789_OK) {
                sensor.graph_updated_at = now;
                sensor.graph_version = version;
            }
        }
        break;
    }
    case SENSOR_FINISH:
        sensor.drawn_state = *state;
        sensor.drawn_color = color;
        sensor.drawn_fill = fill;
        sensor.drawn_history = history;
        sensor.drawn_graph_limit = state->sensor_deviation_limit_deci_deg;
        sensor.first_frame = false;
        sensor.step = SENSOR_CHANNEL_A;
        return true;
    }

    if (result == ST7789_OK) sensor.step++;
    return false;
}
