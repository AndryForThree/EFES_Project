#include "UI_sensor.h"
#include "st7789.h"
#include <stdio.h>

static UI_Graph history_graph;

static const UI_GraphSeriesConfig graph_series[] = {
	{ .color = SENSOR_GRAPH_COLOR, .legend = SENSOR_GRAPH_LEGEND }
};

static const UI_GraphConfig graph_config = {
	.x = SENSOR_GRAPH_X, .y = SENSOR_GRAPH_Y, .width = SENSOR_GRAPH_WIDTH_PX, .height = SENSOR_GRAPH_HEIGHT_PX,
	.color_grid = SENSOR_BORDER, .color_background = SENSOR_GRAPH_BACKGROUND_COLOR,
	.series = graph_series,
	.series_count = sizeof(graph_series) / sizeof(graph_series[0]),
	.capacity = SENSOR_GRAPH_CAPACITY,
	.history_ms = SENSOR_GRAPH_HISTORY_MS,
	.text_color = SENSOR_TITLE,
	.max_digits = SENSOR_GRAPH_MAX_DIGITS,
	.max_decimal_places = SENSOR_GRAPH_MAX_DECIMAL_PLACES,
	.symmetric_scale = SENSOR_GRAPH_SYMMETRIC_SCALE,
	.minimum_scale = SENSOR_GRAPH_MINIMUM_SCALE
};

enum {
	SENSOR_PANELS, SENSOR_LABELS,
	SENSOR_CHANNEL_A, SENSOR_CHANNEL_B,
	SENSOR_DEVIATION_VALUE, SENSOR_DEVIATION_NA, SENSOR_DEVIATION_UNIT, SENSOR_DEVIATION_BAR,
	SENSOR_HISTORY_DOT, SENSOR_HISTORY_TEXT, SENSOR_GRAPH,
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
};

typedef struct {
	App_View render_view;
	App_View drawn_state;
	bool rendering;
	uint8_t step, item;
	bool first_frame;
	App_Page page;
	UI_Header header;
	UI_DeveloperMode developer_mode;
	bool developer_started;
	uint32_t render_started_at_ms;
	uint16_t drawn_color, drawn_fill;
	uint8_t drawn_history;
	char number[16]; /* Scratch buffer used to format numeric fields. */
} UI_SensorContext;

static UI_SensorContext sensor;

static int BarFill(const App_View *state)
{
	/* Fault is a hardware verdict. Numeric saturation alone never changes color. */
	if (!state->sensor.channel_a_valid || !state->sensor.channel_b_valid ||
		state->sensor.plausibility_fault) {
		return SENSOR_DEVIATION_BAR_WIDTH;
	}
	uint32_t fill = (uint32_t)UI_SensorDeviation(&state->sensor) * SENSOR_DEVIATION_BAR_WIDTH /
					state->sensor.deviation_limit_deci_deg;
	return fill > SENSOR_DEVIATION_BAR_WIDTH ? SENSOR_DEVIATION_BAR_WIDTH : (int)fill;
}

static ST7789_Result WriteAngle(uint16_t x, int angle)
{
	int magnitude = angle < 0 ? -angle : angle;
	snprintf(sensor.number, sizeof(sensor.number), "%c%d.%d",
				angle < 0 ? '-' : '+', magnitude / 10, magnitude % 10);
	return ST7789_WriteNumberField(x, 47, 132, sensor.number,
									SENSOR_FONT_ANGLE, SENSOR_TEXT, UI_CARD_BACKGROUND);
}

void UI_Sensor_Init(App_Page page)
{
	sensor = (UI_SensorContext){0};
	sensor.page = page;
	sensor.first_frame = true;
	UI_Graph_init(&history_graph, &graph_config);
}

static void PrepareRender(void)
{
	UI_Header_startRendering(&sensor.header, sensor.page, "SENSOR DIAGNOSTICS");
	sensor.rendering = false;
	sensor.step = SENSOR_PANELS;
	sensor.item = 0;
	sensor.first_frame = true;
}

bool UI_Sensor_Process(const App_View *current, bool draw)
{
	uint16_t current_deviation = UI_SensorDeviation(&current->sensor);
	bool usable = current->sensor.valid && current->sensor.channel_a_valid &&
		current->sensor.channel_b_valid && !current->sensor.plausibility_fault;
	UI_Graph_updateHistory(&history_graph, (UI_GraphSample){
		.values = { current_deviation > INT16_MAX ? INT16_MAX : (int16_t)current_deviation }
	}, usable, HAL_GetTick());
	if (current->page != sensor.page) {
		sensor.first_frame = true;
		sensor.rendering = false;
		return false;
	}
	if (!draw) {
		sensor.rendering = false;
		return false;
	}
	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	if (!sensor.rendering) {
		if (sensor.first_frame) {
			PrepareRender();
		}
		sensor.render_view = *current;
		sensor.render_started_at_ms = HAL_GetTick();
		sensor.developer_started = false;
		if (!sensor.first_frame && sensor.drawn_state.developer_mode && !current->developer_mode) {
			UI_Header_startRendering(&sensor.header, sensor.page, "SENSOR DIAGNOSTICS");
		}
		UI_Graph_startRendering(&history_graph, sensor.first_frame);
		sensor.rendering = true;
	}
	const App_View *state = &sensor.render_view;

	if (!UI_Header_render(&sensor.header)) {
		return false;
	}

	ST7789_Result result = ST7789_OK;
	const App_View *old = &sensor.drawn_state;
	bool first = sensor.first_frame;
	uint16_t deviation = UI_SensorDeviation(&state->sensor);
	/* Freshness is supplied by the source through the stable App_View snapshot. */
	bool invalid = !state->sensor.channel_a_valid || !state->sensor.channel_b_valid;
	bool old_invalid = !old->sensor.channel_a_valid || !old->sensor.channel_b_valid;
	uint16_t color = invalid || state->sensor.plausibility_fault ? SENSOR_FAULT :
						(state->sensor.stale ? SENSOR_STALE : SENSOR_NORMAL);
	bool history_fault = invalid || state->sensor.plausibility_fault;
	uint8_t history = history_fault ? 2 : (state->sensor.stale ? 1 : 0);
	uint16_t history_color = history_fault ? SENSOR_FAULT : (state->sensor.stale ? SENSOR_STALE : SENSOR_NORMAL);
	uint16_t fill = BarFill(state);
	bool value_changed = first || invalid != old_invalid ||
							(!invalid && deviation != UI_SensorDeviation(&old->sensor)) || color != sensor.drawn_color;

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
		case SENSOR_CHANNEL_A:
			if (first || state->sensor.channel_a_angle_deci_deg != old->sensor.channel_a_angle_deci_deg) {
				result = WriteAngle(8, state->sensor.channel_a_angle_deci_deg);
			}
			break;
		case SENSOR_CHANNEL_B:
			if (first || state->sensor.channel_b_angle_deci_deg != old->sensor.channel_b_angle_deci_deg) {
				result = WriteAngle(168, state->sensor.channel_b_angle_deci_deg);
			}
			break;
		case SENSOR_DEVIATION_VALUE:
			if (value_changed) {
				if (invalid) {
					sensor.number[0] = '\0';
				} else {
					snprintf(sensor.number, sizeof(sensor.number), "%u.%u",
								(unsigned)deviation / 10U, (unsigned)deviation % 10U);
				}
				/* Empty numeric field clears the entire digit height before N/A. */
				result = ST7789_WriteNumberField(178, 91, 120, sensor.number,
							SENSOR_FONT_VALUE, color, UI_CARD_BACKGROUND);
			}
			break;
		case SENSOR_DEVIATION_NA:
			if (invalid && value_changed) {
				result = ST7789_WriteTextField(178, 94, 120, "N/A", SENSOR_FONT_NA,
							ST7789_TEXT_RIGHT, SENSOR_FAULT, UI_CARD_BACKGROUND);
			}
			break;
		case SENSOR_DEVIATION_UNIT:
			if (first || invalid != old_invalid || color != sensor.drawn_color) {
				result = ST7789_WriteTextField(300, 91, 10, invalid ? "" : "\xB0",
							SENSOR_FONT_UNIT, ST7789_TEXT_LEFT, color, UI_CARD_BACKGROUND);
			}
			break;
		case SENSOR_DEVIATION_BAR:
			if (first || fill != sensor.drawn_fill || color != sensor.drawn_color) {
				result = ST7789_DrawProgressBar(SENSOR_DEVIATION_BAR_X, SENSOR_DEVIATION_BAR_Y,
							SENSOR_DEVIATION_BAR_WIDTH, SENSOR_DEVIATION_BAR_HEIGHT, fill,
							color, SENSOR_TRACK, UI_CARD_BACKGROUND);
			}
			break;
		case SENSOR_HISTORY_DOT:
			if (first || history != sensor.drawn_history) {
				result = ST7789_DrawFilledCircle(214, 148, 3, history_color, UI_CARD_BACKGROUND);
			}
			break;
		case SENSOR_HISTORY_TEXT:
			if (first || history != sensor.drawn_history) {
				result = ST7789_WriteTextField(224, 141, 83,
							history_fault ? "FAULT" : (state->sensor.stale ? "STALE" : "LIVE"),
							SENSOR_FONT_HISTORY, ST7789_TEXT_RIGHT, history_color, UI_CARD_BACKGROUND);
			}
			break;
		case SENSOR_GRAPH:
			if (!UI_Graph_render(&history_graph)) {
				return false;
			}
			break;
		case SENSOR_FINISH: {
			if (state->developer_mode) {
				if (!sensor.developer_started) {
					uint32_t elapsed_ms = HAL_GetTick() - sensor.render_started_at_ms;
					UI_DeveloperMode_startRendering(&sensor.developer_mode, elapsed_ms,
						sensor.first_frame || !sensor.drawn_state.developer_mode);
					sensor.developer_started = true;
				}
				if (!UI_DeveloperMode_render(&sensor.developer_mode)) {
					return false;
				}
			}
			sensor.drawn_state = *state;
			sensor.drawn_color = color;
			sensor.drawn_fill = fill;
			sensor.drawn_history = history;
			sensor.first_frame = false;
			sensor.step = SENSOR_CHANNEL_A;
			sensor.rendering = false;
			return true;
		}
	}

	if (result == ST7789_OK) {
		sensor.step++;
	}
	return false;
}
