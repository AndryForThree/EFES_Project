#include "UI_steering.h"
#include "st7789.h"
#include <stdio.h>

enum { 
	FEEDBACK_LIVE, 
	FEEDBACK_STALE, 
	FEEDBACK_FAULT 
};

enum {
	RESPONSE_PANELS, RESPONSE_LABELS,
	RESPONSE_REQUESTED, RESPONSE_ACTUAL, RESPONSE_ACTUAL_UNIT,
	RESPONSE_STATUS_DOT, RESPONSE_STATUS_TEXT,
	RESPONSE_GRAPH, RESPONSE_DRIVING_MODE, RESPONSE_FINISH
};

static UI_Graph history_graph;

static const UI_GraphSeriesConfig graph_series[] = {
	{ .color = STEERING_REQUESTED_COLOR, .legend = STEERING_GRAPH_LEGEND_A },
	{ .color = STEERING_ACTUAL_COLOR, .legend = STEERING_GRAPH_LEGEND_B }
};

static const UI_GraphConfig graph_config = {
	.x = STEERING_GRAPH_X, .y = STEERING_GRAPH_Y,
	.width = STEERING_GRAPH_WIDTH_PX, .height = STEERING_GRAPH_HEIGHT_PX,
	.color_grid = STEERING_BORDER, .color_background = STEERING_GRAPH_BACKGROUND_COLOR,
	.series = graph_series,
	.series_count = sizeof(graph_series) / sizeof(graph_series[0]),
	.capacity = STEERING_GRAPH_CAPACITY,
	.history_ms = STEERING_GRAPH_HISTORY_MS,
	.text_color = STEERING_TITLE,
	.max_digits = STEERING_GRAPH_MAX_DIGITS,
	.max_decimal_places = STEERING_GRAPH_MAX_DECIMAL_PLACES,
	.symmetric_scale = STEERING_GRAPH_SYMMETRIC_SCALE,
	.minimum_scale = STEERING_GRAPH_MINIMUM_SCALE
};

static const struct {
	uint16_t x, y, width, height;
} panels[] = {
	{3, 26, 154, 52}, {163, 26, 154, 52}, {3, 83, 314, 116}
};

static const struct {
	uint16_t x, y;
	const char *text;
	FontId font;
	uint16_t color, background;
} labels[] = {
	{12, 30, "REQUESTED", STEERING_FONT_TITLE, STEERING_REQUESTED_COLOR, UI_CARD_BACKGROUND},
	{172, 30, "ACTUAL", STEERING_FONT_TITLE, STEERING_ACTUAL_COLOR, UI_CARD_BACKGROUND},
	{141, 47, "\xB0", STEERING_FONT_LABEL, STEERING_REQUESTED_COLOR, UI_CARD_BACKGROUND},
	{12, 89, "STEERING HISTORY", STEERING_FONT_TITLE, STEERING_TITLE, UI_CARD_BACKGROUND},
};

typedef struct {
	App_View render_view;
	App_View drawn_state;
	bool rendering;
	uint8_t step, item, status, drawn_status;
	bool first_frame;
	App_Page page;
	UI_Header header;
	UI_DeveloperMode developer_mode;
	bool developer_started;
	uint32_t render_started_at_ms;
	UI_DrivingMode driving_mode;
	char number[16];
} UI_SteeringContext;

static UI_SteeringContext response;

void UI_Steering_Init(App_Page page)
{
	response = (UI_SteeringContext){0};
	response.page = page;
	response.first_frame = true;
	UI_Graph_init(&history_graph, &graph_config);
}

static void PrepareRender(void)
{
	UI_Header_startRendering(&response.header, response.page, "STEERING RESPONSE");
	response.rendering = false;
	response.step = RESPONSE_PANELS;
	response.item = 0;
	response.first_frame = true;
}

static ST7789_Result WriteAngle(uint16_t x, int angle, uint16_t color)
{
	int magnitude = angle < 0 ? -angle : angle;
	snprintf(response.number, sizeof(response.number), "%c%d.%d",
				angle < 0 ? '-' : '+', magnitude / 10, magnitude % 10);
	return ST7789_WriteNumberField(x, 47, 132, response.number,
									STEERING_FONT_VALUE, color, UI_CARD_BACKGROUND);
}

bool UI_Steering_Process(const App_View *current, bool draw)
{
	UI_Graph_updateHistory(&history_graph, (UI_GraphSample){
		.values = { current->operating.road_requested_angle_deci_deg, current->road.actual_angle_deci_deg }
	}, current->road.valid, HAL_GetTick());
	if (current->page != response.page) {
		response.first_frame = true;
		response.rendering = false;
		return false;
	}
	if (!draw) {
		response.rendering = false;
		return false;
	}
	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	if (!response.rendering) {
		if (response.first_frame) {
			PrepareRender();
		}
		response.render_view = *current;
		response.render_started_at_ms = HAL_GetTick();
		response.developer_started = false;
		if (!response.first_frame && response.drawn_state.developer_mode && !current->developer_mode) {
			UI_Header_startRendering(&response.header, response.page, "STEERING RESPONSE");
		}
		if (response.first_frame || response.driving_mode.driving_mode != current->drive_mode) {
			UI_DrivingMode_startRendering(&response.driving_mode, current->drive_mode);
		}
		UI_Graph_startRendering(&history_graph, response.first_frame);
		response.rendering = true;
	}
	const App_View *state = &response.render_view;

	if (!UI_Header_render(&response.header)) {
		return false;
	}

	ST7789_Result result = ST7789_OK;
	const App_View *old = &response.drawn_state;
	bool first = response.first_frame;
	if (!state->operating.can_online || !state->road.valid) {
		response.status = FEEDBACK_FAULT;
	} else if (state->road.stale) {
		response.status = FEEDBACK_STALE;
	} else {
		response.status = FEEDBACK_LIVE;
	}
	bool status_changed = first || response.status != response.drawn_status;
	bool fault = response.status == FEEDBACK_FAULT;
	uint16_t status_color = fault ? STEERING_FAULT_COLOR :
		(response.status == FEEDBACK_STALE ? STEERING_STALE_COLOR : STEERING_LIVE_COLOR);
	uint16_t actual_color = response.status == FEEDBACK_LIVE ? STEERING_ACTUAL_COLOR : status_color;

	switch (response.step) {
		case RESPONSE_PANELS:
			result = ST7789_DrawRoundedRectangle(panels[response.item].x, panels[response.item].y,
						panels[response.item].width, panels[response.item].height, 4,
						STEERING_BORDER, UI_CARD_BACKGROUND, UI_BACKGROUND);
			if (result == ST7789_OK && ++response.item == sizeof(panels) / sizeof(panels[0])) {
				response.item = 0;
				response.step++;
			}
			return false;
		case RESPONSE_LABELS:
			result = ST7789_WriteString(labels[response.item].x, labels[response.item].y,
						labels[response.item].text, labels[response.item].font,
						labels[response.item].color, labels[response.item].background);
			if (result == ST7789_OK && ++response.item == sizeof(labels) / sizeof(labels[0])) {
				response.item = 0;
				response.step++;
			}
			return false;
		case RESPONSE_REQUESTED:
			if (first || state->operating.road_requested_angle_deci_deg != old->operating.road_requested_angle_deci_deg) {
				result = WriteAngle(8, state->operating.road_requested_angle_deci_deg, STEERING_REQUESTED_COLOR);
			}
			break;
		case RESPONSE_ACTUAL:
			if (first || status_changed || state->road.actual_angle_deci_deg != old->road.actual_angle_deci_deg) {
				if (fault) {
					result = ST7789_WriteTextField(168, 47, 132, "N/A", STEERING_FONT_VALUE,
								ST7789_TEXT_RIGHT, STEERING_FAULT_COLOR, UI_CARD_BACKGROUND);
				} else {
					result = WriteAngle(168, state->road.actual_angle_deci_deg, actual_color);
			}
			}
			break;
		case RESPONSE_ACTUAL_UNIT:
			if (status_changed) {
				result = ST7789_WriteTextField(301, 47, 10, fault ? "" : "\xB0", STEERING_FONT_LABEL,
							ST7789_TEXT_LEFT, actual_color, UI_CARD_BACKGROUND);
			}
			break;
		case RESPONSE_STATUS_DOT:
			if (status_changed) {
				result = ST7789_DrawFilledCircle(256, 97, 3, status_color, UI_CARD_BACKGROUND);
			}
			break;
		case RESPONSE_STATUS_TEXT:
			if (status_changed) {
				result = ST7789_WriteTextField(266, 90, 41,
							fault ? "FAULT" : (response.status == FEEDBACK_STALE ? "STALE" : "LIVE"),
							STEERING_FONT_STATUS, ST7789_TEXT_RIGHT, status_color, UI_CARD_BACKGROUND);
			}
			break;
		case RESPONSE_GRAPH:
			if (!UI_Graph_render(&history_graph)) {
				return false;
			}
			break;
		case RESPONSE_DRIVING_MODE:
			if (!UI_DrivingMode_render(&response.driving_mode)) {
				return false;
			}
			break;
		case RESPONSE_FINISH: {
			if (state->developer_mode) {
				if (!response.developer_started) {
					uint32_t elapsed_ms = HAL_GetTick() - response.render_started_at_ms;
					UI_DeveloperMode_startRendering(&response.developer_mode, elapsed_ms,
						response.first_frame || !response.drawn_state.developer_mode);
					response.developer_started = true;
				}
				if (!UI_DeveloperMode_render(&response.developer_mode)) {
					return false;
				}
			}
			response.drawn_state = *state;
			response.drawn_status = response.status;
			response.first_frame = false;
			response.step = RESPONSE_REQUESTED;
			response.rendering = false;
			return true;
		}
	}

	if (result == ST7789_OK) {
		response.step++;
	}
	return false;
}
