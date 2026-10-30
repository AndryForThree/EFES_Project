#include "UI_steering.h"
#include "st7789.h"
#include <stdio.h>

#define STEERING_FAULT_COLOR		UI_ERROR_COLOR
#define STEERING_TITLE				UI_TITLE_COLOR
#define STEERING_BORDER				UI_BORDER_COLOR
#define STEERING_REQUESTED_COLOR	UI_YELLOW_COLOR /* Bright yellow. */
#define STEERING_ACTUAL_COLOR		UI_MAGENTA_COLOR /* Bright magenta. */
#define STEERING_LIVE_COLOR			UI_OK_COLOR
#define STEERING_STALE_COLOR		UI_WARNING_COLOR

#define STEERING_FONT_TITLE		FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define STEERING_FONT_VALUE		FONT_RAJDHANI_BOLD_28
#define STEERING_FONT_LABEL		FONT_INTER_MEDIUM_10
#define STEERING_FONT_STATUS	FONT_BARLOW_SEMI_CONDENSED_BOLD_12
#define STEERING_FONT_LEGEND	FONT_BARLOW_SEMI_CONDENSED_BOLD_10
#define STEERING_GRAPH_X		45U
#define STEERING_GRAPH_Y		111U
#define STEERING_GRAPH_HEIGHT_PX	58U

#define STEERING_GRAPH_WIDTH_PX		264
#define STEERING_GRAPH_HISTORY_MS	10000
#define STEERING_GRAPH_REFRESH_MS	100
#define STEERING_GRAPH_MIN_ANGLE	(-450) /* Road wheel angle, tenths of a degree. */
#define STEERING_GRAPH_MAX_ANGLE	450
#define STEERING_GRAPH_SAMPLES		STEERING_GRAPH_WIDTH_PX

enum { 
	FEEDBACK_LIVE, 
	FEEDBACK_STALE, 
	FEEDBACK_FAULT 
};

enum {
	RESPONSE_PANELS, RESPONSE_LABELS, RESPONSE_AXES, RESPONSE_LEGEND,
	RESPONSE_REQUESTED, RESPONSE_ACTUAL, RESPONSE_ACTUAL_UNIT,
	RESPONSE_STATUS_DOT, RESPONSE_STATUS_TEXT,
	RESPONSE_GRAPH, RESPONSE_MODE, RESPONSE_FINISH
};

static ST7789_GraphSample history_samples[STEERING_GRAPH_SAMPLES];
static UI_Trace history_trace;

static const ST7789_Graph graph = {
	.x = STEERING_GRAPH_X, .y = STEERING_GRAPH_Y,
	.width = STEERING_GRAPH_WIDTH_PX, .height = STEERING_GRAPH_HEIGHT_PX,
	.minimum = STEERING_GRAPH_MIN_ANGLE, .maximum = STEERING_GRAPH_MAX_ANGLE,
	.color_a = STEERING_REQUESTED_COLOR, .color_b = STEERING_ACTUAL_COLOR,
	.grid = STEERING_BORDER, .background = UI_CARD_BACKGROUND, .series_count = 2
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
	{104, 185, "REQUESTED", STEERING_FONT_LEGEND, STEERING_REQUESTED_COLOR, UI_CARD_BACKGROUND},
	{194, 185, "ACTUAL", STEERING_FONT_LEGEND, STEERING_ACTUAL_COLOR, UI_CARD_BACKGROUND}
};

static ST7789_GraphSample snapshot[STEERING_GRAPH_SAMPLES];
typedef struct {
	App_View render_view;
	App_View drawn_state;
	bool rendering;
	uint8_t step, item, status, drawn_status;
	bool first_frame;
	App_Page page;
	UI_Header header;
	UI_Developer developer;
	uint32_t render_started_at_ms;
	UI_Mode mode_bar;
	uint32_t graph_updated_at, graph_version;
	char number[16];
	char axis_text[6][16];
} UI_SteeringContext;

static UI_SteeringContext response;

void UI_Steering_Init(App_Page page)
{
	response = (UI_SteeringContext){0};
	response.page = page;
	response.first_frame = true;
	UI_Trace_Init(&history_trace, history_samples, STEERING_GRAPH_SAMPLES, STEERING_GRAPH_HISTORY_MS);
}

static void PrepareRender(void)
{
	UI_Header_Init(&response.header, response.page);
	UI_Developer_Init(&response.developer);
	UI_Mode_Init(&response.mode_bar);
	response.rendering = false;
	response.step = RESPONSE_PANELS;
	response.item = 0;
	response.first_frame = true;
	for (unsigned i = 0; i < 3; i++) {
		int angle = graph.maximum - (graph.maximum - graph.minimum) * (int)i / 2;
		int magnitude = angle < 0 ? -angle : angle;
		if (magnitude % 10 == 0)
			snprintf(response.axis_text[i], 16, "%d\xB0", angle / 10);
		else
			snprintf(response.axis_text[i], 16, "%s%d.%d\xB0",
						angle < 0 ? "-" : "", magnitude / 10, magnitude % 10);
	}
	UI_FormatGraphTime(response.axis_text[3], STEERING_GRAPH_HISTORY_MS);
	UI_FormatGraphTime(response.axis_text[4], STEERING_GRAPH_HISTORY_MS / 2U);
	UI_FormatGraphTime(response.axis_text[5], 0);
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
	UI_Trace_Process(&history_trace, (ST7789_GraphSample){
		current->operating.road_requested_angle_deci_deg, current->road.actual_angle_deci_deg
	}, current->operating.can_online && current->road.valid && !current->road.stale, HAL_GetTick());
	if (current->page != response.page) {
		response.first_frame = true;
		response.rendering = false;
		return false;
	}
	if (!draw) {
		response.rendering = false;
		return false;
	}
	if (ST7789_GetState() != ST7789_STATE_IDLE) return false;

	if (!response.rendering) {
		if (response.first_frame) PrepareRender();
		response.render_view = *current;
		response.render_started_at_ms = HAL_GetTick();
		response.rendering = true;
	}
	const App_View *state = &response.render_view;

	if (!UI_Header_Process(&response.header, "STEERING RESPONSE")) return false;

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
		case RESPONSE_AXES:
			if (response.item < 3) {
				uint16_t y = STEERING_GRAPH_Y + response.item * (STEERING_GRAPH_HEIGHT_PX - 1U) / 2U - 6;
				result = ST7789_WriteTextField(6, y, 35, response.axis_text[response.item],
							STEERING_FONT_LABEL, ST7789_TEXT_RIGHT, STEERING_TITLE, UI_CARD_BACKGROUND);
			} else {
				unsigned tick = response.item - 3;
				uint16_t x = tick == 0 ? STEERING_GRAPH_X : (tick == 1 ?
					STEERING_GRAPH_X + (STEERING_GRAPH_WIDTH_PX - 1U) / 2U - 20 :
					STEERING_GRAPH_X + STEERING_GRAPH_WIDTH_PX - 40);
				ST7789_TextAlign align = tick == 0 ? ST7789_TEXT_LEFT :
											(tick == 1 ? ST7789_TEXT_CENTER : ST7789_TEXT_RIGHT);
				result = ST7789_WriteTextField(x, 171, 40, response.axis_text[response.item],
							STEERING_FONT_LABEL, align, STEERING_TITLE, UI_CARD_BACKGROUND);
			}
			if (result == ST7789_OK && ++response.item == 6) {
				response.item = 0;
				response.step++;
			}
			return false;
		case RESPONSE_LEGEND:
			result = ST7789_DrawFilledRectangle(response.item == 0 ? 86 : 176, 191, 13, 2,
						response.item == 0 ? STEERING_REQUESTED_COLOR : STEERING_ACTUAL_COLOR);
			if (result == ST7789_OK && ++response.item == 2) {
				response.item = 0;
				response.step++;
			}
			return false;
		case RESPONSE_REQUESTED:
			if (first || state->operating.road_requested_angle_deci_deg != old->operating.road_requested_angle_deci_deg)
				result = WriteAngle(8, state->operating.road_requested_angle_deci_deg, STEERING_REQUESTED_COLOR);
			break;
		case RESPONSE_ACTUAL:
			if (first || status_changed || state->road.actual_angle_deci_deg != old->road.actual_angle_deci_deg) {
				if (fault)
					result = ST7789_WriteTextField(168, 47, 132, "N/A", STEERING_FONT_VALUE,
								ST7789_TEXT_RIGHT, STEERING_FAULT_COLOR, UI_CARD_BACKGROUND);
				else
					result = WriteAngle(168, state->road.actual_angle_deci_deg, actual_color);
			}
			break;
		case RESPONSE_ACTUAL_UNIT:
			if (status_changed)
				result = ST7789_WriteTextField(301, 47, 10, fault ? "" : "\xB0", STEERING_FONT_LABEL,
							ST7789_TEXT_LEFT, actual_color, UI_CARD_BACKGROUND);
			break;
		case RESPONSE_STATUS_DOT:
			if (status_changed)
				result = ST7789_DrawFilledCircle(256, 97, 3, status_color, UI_CARD_BACKGROUND);
			break;
		case RESPONSE_STATUS_TEXT:
			if (status_changed)
				result = ST7789_WriteTextField(266, 90, 41,
							fault ? "FAULT" : (response.status == FEEDBACK_STALE ? "STALE" : "LIVE"),
							STEERING_FONT_STATUS, ST7789_TEXT_RIGHT, status_color, UI_CARD_BACKGROUND);
			break;
		case RESPONSE_GRAPH: {
			uint32_t now = HAL_GetTick();
			if (first || (history_trace.version != response.graph_version &&
				(uint32_t)(now - response.graph_updated_at) >= STEERING_GRAPH_REFRESH_MS)) {
				uint16_t count = UI_Trace_Copy(&history_trace, snapshot);
				result = ST7789_DrawGraph(&graph, snapshot, count);
				if (result == ST7789_OK) {
					response.graph_version = history_trace.version;
					response.graph_updated_at = now;
				}
			}
			break;
		}
		case RESPONSE_MODE:
			if (!UI_Mode_Process(&response.mode_bar, state->drive_mode)) return false;
			break;
		case RESPONSE_FINISH: {
			uint32_t elapsed_ms = HAL_GetTick() - response.render_started_at_ms;
			if (!UI_Developer_Process(&response.developer, state->developer_mode != 0, elapsed_ms)) return false;
			response.drawn_state = *state;
			response.drawn_status = response.status;
			response.first_frame = false;
			response.step = RESPONSE_REQUESTED;
			response.rendering = false;
			return true;
		}
	}

	if (result == ST7789_OK) response.step++;
	return false;
}
