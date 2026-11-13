#include "UI_home.h"
#include "st7789.h"
#include <stdio.h>
#include <string.h>

enum {
	HOME_CARDS,			 
	HOME_RULE,
	HOME_DIRECTION_RULE,
	HOME_LABELS,
	HOME_SYMBOLS,
	HOME_STATUS,
	HOME_WHEEL,
	HOME_ANGLE,
	HOME_DIRECTION,
	HOME_BAR,
	HOME_SPEED,
	HOME_SENSOR_DELTA,
	HOME_CAN_STATUS,
	HOME_ACTUATOR_STATUS,
	HOME_STEERING_RATIO,
	HOME_DRIVING_MODE,
	HOME_DEVELOPER_RENDER
};

// Define the main informative Cards in the page
typedef struct {
	uint16_t	x0, y0, x1, y1;
} UI_HomeCard;

static const UI_HomeCard cards[] = {
	{3, 48, 316, 148},
	{3, 153, 103, 199},
	{109, 153, 209, 199}, 
	{215, 153, 316, 199}
};

// Define all fixed labels in the Page
typedef struct {
	uint16_t	x, y;				// Position of the label
	const char*	text;				// Text to be written in the label
	FontId		font;				// Font of the Label
	uint16_t	width; 				// If > 0, it defines the width of the assigned text cell, so it is possibile to align the text at center, right or left
	uint16_t	background, color;	// Main and Background color of the label
} UI_HomeLabel;

static const UI_HomeLabel labels[] = {
	{28, 26, "SENSORS", HOME_FONT_STATUS, 0, UI_BACKGROUND, HOME_TEXT_COLOR},
	{152, 26, "CAN", HOME_FONT_STATUS, 0, UI_BACKGROUND, HOME_TEXT_COLOR},
	{252, 26, "ROAD ECU", HOME_FONT_STATUS, 0, UI_BACKGROUND, HOME_TEXT_COLOR},
	{122, 54, "STEERING REQUEST", HOME_FONT_TITLE, 192, UI_CARD_BACKGROUND, HOME_TITLE_COLOR},
	{254, 80, "\xB0", HOME_FONT_LABEL, 0, UI_CARD_BACKGROUND, HOME_MUTED_COLOR},
	{32, 157, "SPEED", HOME_FONT_CARD_TITLE, 0, UI_CARD_BACKGROUND, HOME_TITLE_COLOR},
	{61, 185, "km/h", HOME_FONT_LABEL, 0, UI_CARD_BACKGROUND, HOME_MUTED_COLOR},
	{138, 157, "DELTA", HOME_FONT_CARD_TITLE, 0, UI_CARD_BACKGROUND, HOME_TITLE_COLOR},
	{195, 179, "\xB0", HOME_FONT_LABEL, 0, UI_CARD_BACKGROUND, HOME_MUTED_COLOR},
	{290, 177, ":1", HOME_FONT_NUMBER, 0, UI_CARD_BACKGROUND, HOME_MUTED_COLOR},
	{244, 157, "MAP", HOME_FONT_CARD_TITLE, 0, UI_CARD_BACKGROUND, HOME_TITLE_COLOR},
};

// Define all Graphic Symbols to be used in the page
typedef struct {
	uint16_t		x, y;
	GraphicAssetId	symbol;
	uint16_t		background;
} UI_HomeSymbol;

static const UI_HomeSymbol symbols[] = {
	{8, 155, ASSET_SPEED, UI_CARD_BACKGROUND},
	{114, 155, ASSET_SENSOR_DELTA, UI_CARD_BACKGROUND},
	{220, 155, ASSET_STEERING_MAP, UI_CARD_BACKGROUND},
};

static const UI_SegmentedBarConfig bar_config = {
	.x					= HOME_BAR_X,
	.width				= HOME_BAR_WIDTH,
	.y					= HOME_BAR_Y,
	.height				= HOME_BAR_HEIGHT,
	.segment_gap		= HOME_BAR_SEGMENT_GAP,
	.segments_per_side	= HOME_BAR_SEGMENTS_PER_SIDE,
	.center_gap			= HOME_BAR_CENTER_GAP,
	.zero_width			= HOME_BAR_ZERO_WIDTH,
	.zero_extension		= HOME_BAR_ZERO_EXTENSION,
	.full_scale			= HOME_BAR_FULL_SCALE,
	.color_fill			= HOME_BAR_FILL_COLOR,
	.color_track		= HOME_BAR_TRACK_COLOR,
	.color_zero			= HOME_BAR_ZERO_COLOR,
	.value_divisor		= HOME_BAR_VALUE_DIVISOR,
	.decimal_places		= HOME_BAR_DECIMAL_PLACES,
	.unit				= HOME_BAR_UNIT,
	.label_font			= HOME_BAR_LABEL_FONT,
	.label_min_gap		= HOME_BAR_LABEL_MIN_GAP,
	.label_gap			= HOME_BAR_LABEL_GAP,
	.color_label		= HOME_BAR_LABEL_COLOR,
	.color_background	= HOME_BAR_BACKGROUND_COLOR
};

// UI Home Page run-time state
typedef struct {
	App_View 			render_view;			// Stable copy of the App state used for current rendering process
	App_View 			drawn_state;			// App state rendered previously, so it is possibile to recognise what actually changed
	bool 				rendering;				// Is the rendering ongoing?
	uint8_t 			step;					// Current rendering phase
	uint8_t 			item;					// Currently rendered item inside a phase
	bool 				first_frame;			// Is this the first time the Page is Rendered (static items must be drawn in addition to the dynamic ones)
	App_Page 			page;					// Page ID assigned from App to the Page, so this page can recognise when it is selected
	
	// State of graphical items used in the page
	UI_SegmentedBar		bar;
	UI_Header 			header;					 
	UI_DeveloperMode 	developer_mode;			
	UI_DrivingMode 		driving_mode;			

	uint32_t 			render_started_at_ms;	 // Timestamp of the page rendering start (used by Developer Mode Item) 
} UI_HomeContext;

static UI_HomeContext home;

/* Pixel-width fields clear old text and center using the actual glyph metrics. */
static void WriteField(uint16_t x, uint16_t y, uint16_t width,
								FontId font, const char *value, uint16_t color)
{
	ST7789_WriteTextField(	x, y, width, value, font, ST7789_TEXT_CENTER,
							color, UI_CARD_BACKGROUND);
}

static bool SensorValid(const Sensor_State *state)
{
	return state->valid && state->channel_a_valid &&
		state->channel_b_valid && !state->plausibility_fault;
}

void UI_Home_Init(App_Page page)
{
	home = (UI_HomeContext){0};
	home.page = page;
	home.first_frame = true;
	UI_SegmentedBar_init(&home.bar, &bar_config);
}

static void PrepareRender(void) {
	UI_Header_startRendering(&home.header, home.page, "HOME");
	home.rendering = false;
	home.step = HOME_CARDS;
	home.item = 0;
	home.first_frame = true;
}

bool UI_Home_Process(const App_View *current, bool draw) {
	// If this page is not currently selected, prepare the next rendering to 
	// be a fist time rendering (all static objects must be re-rendered)
	if (current->page != home.page) {
		home.first_frame = true;
		home.rendering = false;
		return false;
	}

	// Check if the page has not the permission to render
	if (!draw) {
		home.rendering = false;
		return false;
	}

	// Render only if the ST7789 is free
	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	if (!home.rendering) {
		if (home.first_frame) {
			PrepareRender();
		}
		home.render_view = *current;
		home.render_started_at_ms = HAL_GetTick();
		if (!home.first_frame && home.drawn_state.developer_mode && !current->developer_mode) {
			UI_Header_startRendering(&home.header, home.page, "HOME");
		}
		if (home.first_frame || home.driving_mode.driving_mode != current->drive_mode) {
			UI_DrivingMode_startRendering(&home.driving_mode, current->drive_mode);
		}
		UI_SegmentedBar_startRendering(&home.bar,
			home.render_view.operating.steering_angle_deci_deg, home.first_frame);
		home.rendering = true;
	}
	const App_View *state = &home.render_view;

	if (!UI_Header_render(&home.header)) {
		return false;
	}

	const App_View *old = &home.drawn_state;
	int angle = state->operating.steering_angle_deci_deg;
	uint16_t sensor_delta = UI_SensorDeviation(&state->sensor);
	bool sensors_valid = SensorValid(&state->sensor);
	bool old_sensors_valid = SensorValid(&old->sensor);
	bool first = home.first_frame;

	switch (home.step) {
		case HOME_CARDS:
			ST7789_DrawRoundedRectangle(	cards[home.item].x0, cards[home.item].y0,
											cards[home.item].x1 - cards[home.item].x0 + 1,
											cards[home.item].y1 - cards[home.item].y0 + 1,
											4, HOME_BORDER_COLOR, UI_CARD_BACKGROUND, UI_BACKGROUND);
			home.item++;
			if (home.item == sizeof(cards) / sizeof(cards[0])) {
				home.item = 0;
				home.step++;
			}
			return false;

		case HOME_RULE:
			ST7789_DrawFilledRectangle(119, 55, 1, 86, HOME_BORDER_COLOR);
			home.step++;
			break;

		case HOME_DIRECTION_RULE:
			ST7789_DrawFilledRectangle(264, 76, 1, 37, HOME_BORDER_COLOR);
			home.step++;
			break;

		case HOME_LABELS:
			if (labels[home.item].width != 0) {
				WriteField(	labels[home.item].x, labels[home.item].y,
							labels[home.item].width, labels[home.item].font,
							labels[home.item].text, labels[home.item].color);
			} else {
				ST7789_WriteString(	labels[home.item].x, labels[home.item].y,
									labels[home.item].text, labels[home.item].font,
									labels[home.item].color,
									labels[home.item].background);
			}
			home.item++;
			if (home.item == sizeof(labels) / sizeof(labels[0])) {
				home.item = 0;
				home.step++;
			}
			return false;

		case HOME_SYMBOLS:
			ST7789_DrawSymbol(	symbols[home.item].x, symbols[home.item].y,
								symbols[home.item].symbol, HOME_CARD_SYMBOL_COLOR,
								symbols[home.item].background);
			home.item++;
			if (home.item == sizeof(symbols) / sizeof(symbols[0])) {
				home.item = 0;
				home.step++;
			}
			return false;

		case HOME_STATUS:
			if (first || sensors_valid != old_sensors_valid) {
				ST7789_DrawSymbol(	6, 26,
									sensors_valid ? ASSET_TICK : ASSET_CROSS,
									sensors_valid ? HOME_STATUS_OK_COLOR : HOME_STATUS_ERROR_COLOR,
									UI_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_WHEEL:
			/* One-degree visual resolution avoids retransmitting identical poses. */
			if (first || angle / 10 != old->operating.steering_angle_deci_deg / 10) {
				ST7789_DrawAsset(	18, 59, HOME_WHEEL_ASSET,
									(angle / 10) * 10, UI_CARD_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_ANGLE:
			if (first || angle != old->operating.steering_angle_deci_deg) {
				char number[16];
				int magnitude = angle < 0 ? -angle : angle;
				snprintf(number, sizeof(number), "%c%d.%d",
							angle < 0 ? '-' : '+', magnitude / 10, magnitude % 10);
				ST7789_WriteNumberField(	121, 80, 132, number,
											HOME_FONT_ANGLE, HOME_TEXT_COLOR, UI_CARD_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_DIRECTION:
			if (first || (angle > 0) != (old->operating.steering_angle_deci_deg > 0) ||
				(angle < 0) != (old->operating.steering_angle_deci_deg < 0)) {
				ST7789_WriteTextField(	269, 98, 47,
										angle > 0 ? "RIGHT" : (angle < 0 ? "LEFT" : "ZERO"),
										HOME_FONT_DIRECTION, ST7789_TEXT_LEFT,
										HOME_TITLE_COLOR, UI_CARD_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_BAR:
			if (!UI_SegmentedBar_render(&home.bar)) {
				return false;
			}
			home.step++;
			break;

		case HOME_SPEED:
			if (first || state->operating.vehicle_speed_kmh != old->operating.vehicle_speed_kmh) {
				char number[16];
				snprintf(number, sizeof(number), "%u", (unsigned)state->operating.vehicle_speed_kmh);
				ST7789_WriteNumberField(	9, 177, 48, number,
											HOME_FONT_NUMBER, HOME_TEXT_COLOR, UI_CARD_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_SENSOR_DELTA:
			if (first || sensor_delta != UI_SensorDeviation(&old->sensor) ||
				sensors_valid != old_sensors_valid) {
				char number[16];
				if (sensors_valid) {
					snprintf(number, sizeof(number), "%u.%u",
								(unsigned)sensor_delta / 10U,
								(unsigned)sensor_delta % 10U);
				} else {
					strcpy(number, "--.-");
				}
				ST7789_WriteNumberField(	130, 177, 64, number,
											HOME_FONT_NUMBER, HOME_TEXT_COLOR, UI_CARD_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_CAN_STATUS:
			if (first || state->operating.can_online != old->operating.can_online) {
				ST7789_DrawSymbol(	130, 26,
									state->operating.can_online ? ASSET_TICK : ASSET_CROSS,
									state->operating.can_online ? HOME_STATUS_OK_COLOR : HOME_STATUS_ERROR_COLOR,
									UI_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_ACTUATOR_STATUS:
			if (first || state->operating.actuator_ready != old->operating.actuator_ready) {
				ST7789_DrawSymbol(	230, 26,
									state->operating.actuator_ready ? ASSET_TICK : ASSET_CROSS,
									state->operating.actuator_ready ? HOME_STATUS_OK_COLOR : HOME_STATUS_ERROR_COLOR,
									UI_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_STEERING_RATIO:
			if (first || state->operating.steering_ratio_deci != old->operating.steering_ratio_deci) {
				char number[16];
				snprintf(number, sizeof(number), "%u.%u",
							(unsigned)state->operating.steering_ratio_deci / 10U,
							(unsigned)state->operating.steering_ratio_deci % 10U);
				ST7789_WriteNumberField(	218, 177, 72, number,
											HOME_FONT_NUMBER, HOME_TEXT_COLOR, UI_CARD_BACKGROUND);
			}
			home.step++;
			break;

		case HOME_DRIVING_MODE:
			if (!UI_DrivingMode_render(&home.driving_mode)) {
				return false;
			}
			if (state->developer_mode) {
				uint32_t elapsed_ms = HAL_GetTick() - home.render_started_at_ms;
				UI_DeveloperMode_startRendering(&home.developer_mode, elapsed_ms,
					home.first_frame || !home.drawn_state.developer_mode);
			}
			home.step++;
			break;

		case HOME_DEVELOPER_RENDER:
			if (state->developer_mode && !UI_DeveloperMode_render(&home.developer_mode)) {
				return false;
			}
			home.drawn_state = *state;
			home.first_frame = false;
			home.step = HOME_STATUS;
			home.rendering = false;
			return true;
	}

	return false;
}
