#include "UI_items.h"
#include "UI_private.h"
#include <stdio.h>
#include <string.h>

uint16_t UI_SensorDeviation(const Sensor_State *state) {
	int32_t difference = (int32_t)state->channel_a_angle_deci_deg - state->channel_b_angle_deci_deg;
	return (uint16_t)(difference < 0 ? -difference : difference);
}

// =======================================================================
// 									Header
// =======================================================================


#define HEADER_CONTENT_HEIGHT	(HEADER_HEIGHT - HEADER_BORDER_HEIGHT)
#define HEADER_TITLE_Y			((HEADER_CONTENT_HEIGHT - Fonts[HEADER_FONT].height) / 2)
#define HEADER_DOT_Y			(HEADER_CONTENT_HEIGHT / 2)

void UI_Header_startRendering(UI_Header *header, App_Page page, const char *title) {
	// Check if the Page Name fits in the given space
	size_t length = strlen(title);
	if (length >= sizeof(header->title)) {
		Error_Handler();
		return;
	}

	// Prepare the header data structure (define what needs to be rendered)
	*header			= (UI_Header){0};			// Reset the state of the Header Rendering 
	header->page	= page;						// Set the number of page of the Header
	header->count	= APP_PAGE_COUNT;			// Set the total numer of pages in the UI
	memcpy(header->title, title, length + 1);	// Set the header title!
}

bool UI_Header_render(UI_Header *header) {
	// If the Header rendering is called again after it finishes, it continues to return 
	// the finish flag!
	if (header->drawn) {
		return true;
	}

	// If the Display Driver is busy, just do nothing (wait for it to be free)
	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	// Execute the Rendering process in steps, drawing each graphic element separately
	// This method is not very efficient, but the header is drawn only one time when the Page
	// is entered, so it is preferrable a simpler code!
	switch (header->step) {
		case 0:
			// Draw the background of the header
			ST7789_DrawFilledRectangle(	0, 
										0, 
										ST7789_WIDTH, 
										HEADER_HEIGHT, 
										HEADER_BACKGROUND_COLOR);
			header->step++;
			break;
			
		case 1:
			// Draw the bottom line of header
			ST7789_DrawFilledRectangle(	0, 
										HEADER_HEIGHT - HEADER_BORDER_HEIGHT,
										ST7789_WIDTH, 
										HEADER_BORDER_HEIGHT, 
										HEADER_BORDER_COLOR);
			header->step++;
			break;

		case 2:
			// Draw the header title
			ST7789_WriteString(	HEADER_TITLE_X, 
								HEADER_TITLE_Y, 
								header->title, 
								HEADER_FONT,
								HEADER_TEXT_COLOR, 
								HEADER_BACKGROUND_COLOR);
			header->step++;
			break;
			
		case 3:
			// Draw the header dots
			ST7789_DrawFilledCircle(	ST7789_WIDTH - HEADER_DOT_RIGHT_MARGIN - ((header->count - 1 - header->dot) * HEADER_DOT_SPACING),
										HEADER_DOT_Y,
										header->dot == header->page ? HEADER_DOT_ACTIVE_RADIUS : HEADER_DOT_RADIUS,
										header->dot == header->page ? HEADER_DOT_ACTIVE_COLOR : HEADER_DOT_INACTIVE_COLOR,
										HEADER_BACKGROUND_COLOR);
			header->dot++;
			// Advance to the next step only when all the Circles are drawn
			if (header->dot == header->count) {
				header->step++;
			}
			return false;

		default:
			header->drawn = true;
			return true;
	}
	return false;
}

// =======================================================================
// Driving mode
// =======================================================================

// Define at Compile time all constant parameters
#define DRIVING_MODE_WIDTH				(ST7789_WIDTH - 2 * DRIVING_MODE_X)
#define DRIVING_MODE_ICON_Y				(DRIVING_MODE_Y + (DRIVING_MODE_HEIGHT - Assets[ASSET_DRIVE_MODE].height) / 2)
#define DRIVING_MODE_TEXT_Y				(DRIVING_MODE_Y + (DRIVING_MODE_HEIGHT - Fonts[DRIVING_MODE_FONT].height) / 2)
#define DRIVING_MODE_SEPARATOR_Y		(DRIVING_MODE_Y + DRIVING_MODE_SEPARATOR_VERTICAL_MARGIN)
#define DRIVING_MODE_SEPARATOR_HEIGHT	(DRIVING_MODE_HEIGHT - 2 * DRIVING_MODE_SEPARATOR_VERTICAL_MARGIN)

typedef struct {
	const char *text;
	uint16_t color;
} UI_DrivingModeStyle;

static const UI_DrivingModeStyle driving_modes[] = {
	[APP_DRIVE_NORMAL]	= {"COMFORT", DRIVING_MODE_COMFORT_COLOR},
	[APP_DRIVE_ECO]		= {"ECO", DRIVING_MODE_ECO_COLOR},
	[APP_DRIVE_SPORT]	= {"SPORT", DRIVING_MODE_SPORT_COLOR}
};

void UI_DrivingMode_startRendering(UI_DrivingMode *driving_mode, App_DriveMode driving_mode_value) {
	// Prepare the drive mode data structure (define what needs to be rendered)
	*driving_mode = (UI_DrivingMode){0};
	driving_mode->driving_mode = driving_mode_value;

	// Center the icon and text as a single group
	ST7789_TextSize size;
	ST7789_MeasureText (driving_modes[driving_mode_value].text, DRIVING_MODE_FONT, &size);
	uint16_t icon_width = Assets[ASSET_DRIVE_MODE].width;
	
	driving_mode->symbol_x = DRIVING_MODE_X + (DRIVING_MODE_WIDTH - icon_width - DRIVING_MODE_ICON_TEXT_GAP - size.width) / 2;
	driving_mode->text_x = driving_mode->symbol_x + icon_width + DRIVING_MODE_ICON_TEXT_GAP;
}

bool UI_DrivingMode_render(UI_DrivingMode *driving_mode) {
	if (driving_mode->drawn) {
		return true;
	}

	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	uint16_t color = driving_modes[driving_mode->driving_mode].color;
	switch (driving_mode->step) {
		case 0:
			// Draw the background of the drive mode
			ST7789_DrawRoundedRectangle(	DRIVING_MODE_X,
											DRIVING_MODE_Y,
											DRIVING_MODE_WIDTH,
											DRIVING_MODE_HEIGHT,
											DRIVING_MODE_CORNER_RADIUS,
											color,
											color,
											DRIVING_MODE_BACKGROUND_COLOR);
			driving_mode->step++;
			break;

		case 1:
			// Draw the drive mode icon
			ST7789_DrawAsset(	driving_mode->symbol_x,
								DRIVING_MODE_ICON_Y,
								ASSET_DRIVE_MODE,
								0,
								color);
			driving_mode->step++;
			break;

		case 2:
			// Draw the separator between icon and text
			ST7789_DrawFilledRectangle(	driving_mode->symbol_x + Assets[ASSET_DRIVE_MODE].width +
										(DRIVING_MODE_ICON_TEXT_GAP - DRIVING_MODE_SEPARATOR_WIDTH) / 2,
										DRIVING_MODE_SEPARATOR_Y,
										DRIVING_MODE_SEPARATOR_WIDTH,
										DRIVING_MODE_SEPARATOR_HEIGHT,
										DRIVING_MODE_SEPARATOR_COLOR);
			driving_mode->step++;
			break;

		case 3:
			// Draw the drive mode text
			ST7789_WriteString(	driving_mode->text_x,
								DRIVING_MODE_TEXT_Y,
								driving_modes[driving_mode->driving_mode].text,
								DRIVING_MODE_FONT,
								DRIVING_MODE_TEXT_COLOR,
								color);
			driving_mode->step++;
			break;

		default:
			driving_mode->drawn = true;
			return true;
	}
	return false;
}

// =======================================================================
// Developer mode rendering time
// =======================================================================

#define DEVELOPER_MODE_Y	((HEADER_CONTENT_HEIGHT - Fonts[DEVELOPER_MODE_FONT].height) / 2)

void UI_DeveloperMode_startRendering(UI_DeveloperMode *developer_mode, uint32_t elapsed_ms, bool first_draw) {
	developer_mode->drawn = !first_draw && developer_mode->drawn_elapsed_ms == elapsed_ms;
	if (first_draw) {
		developer_mode->step = 0;	// Draw all the
	} else {
		developer_mode->step = 2;
	}
	developer_mode->elapsed_ms = elapsed_ms;

	if (first_draw) {
		ST7789_TextSize size;
		ST7789_MeasureText("Rend.:", DEVELOPER_MODE_FONT, &size);
		developer_mode->label_width = size.width;
		ST7789_MeasureText("ms", DEVELOPER_MODE_FONT, &size);
		developer_mode->unit_width = size.width;
	}
}

bool UI_DeveloperMode_render(UI_DeveloperMode *developer_mode) {
	if (developer_mode->drawn) {
		return true;
	}

	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	switch (developer_mode->step) {
		case 0:
			// Draw the fixed label only on the first draw
			ST7789_WriteTextField(	DEVELOPER_MODE_X,
									DEVELOPER_MODE_Y,
									developer_mode->label_width + DEVELOPER_MODE_TEXT_GAP,
									"Rend.:",
									DEVELOPER_MODE_FONT,
									ST7789_TEXT_LEFT,
									DEVELOPER_MODE_TEXT_COLOR,
									DEVELOPER_MODE_BACKGROUND_COLOR);
			developer_mode->step++;
			break;

		case 1:
			// Draw the fixed unit only on the first draw
			ST7789_WriteTextField(	DEVELOPER_MODE_X + DEVELOPER_MODE_WIDTH - developer_mode->unit_width - DEVELOPER_MODE_TEXT_GAP,
									DEVELOPER_MODE_Y,
									developer_mode->unit_width + DEVELOPER_MODE_TEXT_GAP,
									"ms",
									DEVELOPER_MODE_FONT,
									ST7789_TEXT_RIGHT,
									DEVELOPER_MODE_TEXT_COLOR,
									DEVELOPER_MODE_BACKGROUND_COLOR);
			developer_mode->step++;
			break;

		case 2: {
			// Update only the numeric field, keeping its right edge fixed
			char text[16];
			snprintf(text, sizeof(text), "%lu", (unsigned long)developer_mode->elapsed_ms);

			ST7789_WriteTextField(	DEVELOPER_MODE_X + developer_mode->label_width + DEVELOPER_MODE_TEXT_GAP,
									DEVELOPER_MODE_Y,
									DEVELOPER_MODE_WIDTH - developer_mode->label_width - developer_mode->unit_width - 2 * DEVELOPER_MODE_TEXT_GAP,
									text,
									DEVELOPER_MODE_FONT,
									ST7789_TEXT_RIGHT,
									DEVELOPER_MODE_TEXT_COLOR,
									DEVELOPER_MODE_BACKGROUND_COLOR);
			developer_mode->step++;
			break;
		}

		default:
			/* The field accepted on the previous call has now finished transferring. */
			developer_mode->drawn_elapsed_ms = developer_mode->elapsed_ms;
			developer_mode->drawn = true;
			return true;
	}
	return false;
}

// =======================================================================
// Segmented bar
// =======================================================================

// Segment widths share all available pixels, including any division remainder.
static void UI_SegmentedBar_segmentGeometry(const UI_SegmentedBar *bar, uint16_t segment,
	uint16_t *x, uint16_t *width, uint16_t *offset, uint16_t *side) {
	const UI_SegmentedBarConfig *config = bar->config;
	uint16_t distance;
	if (segment < config->segments_per_side) {
		*side = 0;
		distance = config->segments_per_side - 1 - segment;
	} else {
		*side = 1;
		distance = segment - config->segments_per_side;
	}
	*offset = (uint32_t)distance * bar->fill_width[*side] / config->segments_per_side;
	uint16_t end = (uint32_t)(distance + 1) * bar->fill_width[*side] / config->segments_per_side;
	*width = end - *offset;
	if (*side == 0) {
		*x = bar->center_x - config->center_gap - end - distance * config->segment_gap;
	} else {
		*x = bar->center_x + config->zero_width + config->center_gap +
			*offset + distance * config->segment_gap;
	}
}

static uint16_t UI_SegmentedBar_segmentFill(const UI_SegmentedBar *bar, int16_t value,
	uint16_t side, uint16_t offset, uint16_t width) {
	int32_t magnitude = 0;
	if (side == 0 && value < 0) {
		magnitude = -(int32_t)value;
	} else if (side == 1 && value > 0) {
		magnitude = value;
	}
	int32_t fill = magnitude * bar->fill_width[side] / bar->config->full_scale - offset;
	if (fill < 0) {
		fill = 0;
	}
	if (fill > width) {
		fill = width;
	}
	return fill;
}

static int16_t UI_SegmentedBar_labelValue(const UI_SegmentedBar *bar, uint16_t label) {
	if (label == 0) {
		return -bar->config->full_scale;
	}
	if (label == bar->label_count - 1) {
		return bar->config->full_scale;
	}
	return ((int32_t)label - bar->label_count / 2) * bar->label_step;
}

static void UI_SegmentedBar_formatLabel(const UI_SegmentedBar *bar, int16_t value, char *text, size_t size) {
	const UI_SegmentedBarConfig *config = bar->config;
	uint32_t factor = 1;
	for (uint8_t digit = 0; digit < config->decimal_places; digit++) {
		factor *= 10;
	}
	uint32_t magnitude = value;
	const char *sign = "";
	if (value < 0) {
		magnitude = -(int32_t)value;
	}
	uint32_t scaled = (magnitude * factor + config->value_divisor / 2) / config->value_divisor;
	if (value < 0 && scaled != 0) {
		sign = "-";
	}
	if (config->decimal_places == 0) {
		snprintf(text, size, "%s%lu%s", sign, (unsigned long)scaled, config->unit);
	} else {
		snprintf(text, size, "%s%lu.%0*lu%s", sign, (unsigned long)(scaled / factor),
			config->decimal_places, (unsigned long)(scaled % factor), config->unit);
	}
}

static uint16_t UI_SegmentedBar_labelX(const UI_SegmentedBar *bar, int16_t value, uint16_t width) {
	const UI_SegmentedBarConfig *config = bar->config;
	int32_t center = bar->center_x + config->zero_width / 2;
	int32_t position;
	if (value < 0) {
		position = center + (int32_t)value * (center - config->x) / config->full_scale;
	} else {
		position = center + (int32_t)value * (config->x + config->width - 1 - center) / config->full_scale;
	}
	position -= width / 2;
	if (position < config->x) {
		position = config->x;
	}
	if (position + width > config->x + config->width) {
		position = config->x + config->width - width;
	}
	return position;
}

// Check the actual text widths before selecting a fixed label layout.
static bool UI_SegmentedBar_labelsFit(const UI_SegmentedBar *bar) {
	const UI_SegmentedBarConfig *config = bar->config;
	uint32_t previous_end = 0;
	char previous_text[32] = "";
	for (uint16_t label = 0; label < bar->label_count; label++) {
		int16_t value = UI_SegmentedBar_labelValue(bar, label);
		char text[32];
		UI_SegmentedBar_formatLabel(bar, value, text, sizeof(text));
		ST7789_TextSize size;
		ST7789_MeasureText(text, config->label_font, &size);
		if (size.width > config->width) {
			return false;
		}
		uint16_t x = UI_SegmentedBar_labelX(bar, value, size.width);
		if (label != 0 && x < previous_end + config->label_min_gap) {
			return false;
		}
		// Avoid labels that round to the same displayed number.
		if (label != 0 && strcmp(text, previous_text) == 0) {
			return false;
		}
		strcpy(previous_text, text);
		previous_end = x + size.width;
	}
	return true;
}

void UI_SegmentedBar_init(UI_SegmentedBar *bar, const UI_SegmentedBarConfig *config) {
	int32_t marker_height = (int32_t)config->height - Fonts[config->label_font].height - config->label_gap;
	int32_t side_width = ((int32_t)config->width - config->zero_width) / 2;
	int32_t gaps = config->center_gap + (config->segments_per_side - 1) * config->segment_gap;
	if (config->full_scale <= 0 || config->value_divisor == 0 || config->decimal_places > SEGMENTED_BAR_MAX_DECIMAL_PLACES ||
		config->segments_per_side == 0 || config->zero_width == 0 ||
		marker_height <= 2 * config->zero_extension || side_width - gaps < config->segments_per_side ||
		(uint32_t)config->x + config->width > ST7789_WIDTH ||
		(uint32_t)config->y + config->height > ST7789_HEIGHT) {
		Error_Handler();
		return;
	}
	*bar = (UI_SegmentedBar){0};
	bar->config = config;
	bar->center_x = config->x + side_width;
	bar->segment_height = marker_height - 2 * config->zero_extension;
	bar->fill_width[0] = side_width - gaps;
	bar->fill_width[1] = config->width - config->zero_width - side_width - gaps;

	// Try increasingly spaced labels using readable intervals: 1, 2, 5, 10, 20, 50...
	uint32_t step = 1;
	uint32_t decade = 1;
	while (true) {
		if (step > config->full_scale) {
			step = config->full_scale;
		}
		bar->label_step = step;
		bar->label_count = 2 * ((config->full_scale - 1) / step) + 3;
		if (UI_SegmentedBar_labelsFit(bar)) {
			break;
		}
		if (step == config->full_scale) {
			Error_Handler();
			return;
		}
		if (step == decade) {
			step = 2 * decade;
		} else if (step == 2 * decade) {
			step = 5 * decade;
		} else {
			decade *= 10;
			step = decade;
		}
	}
}

void UI_SegmentedBar_startRendering(UI_SegmentedBar *bar, int32_t value, bool first_draw) {
	// Limit the captured value to the range represented by the bar.
	if (value > bar->config->full_scale) {
		value = bar->config->full_scale;
	}
	if (value < -bar->config->full_scale) {
		value = -bar->config->full_scale;
	}
	bar->value = value;
	bar->segment = 0;
	bar->label = 0;
	bar->drawn = !first_draw && bar->value == bar->drawn_value;
	if (first_draw) {
		bar->step = 0;
		bar->drawn_value = 0;
	} else {
		bar->step = 3;
	}
}

bool UI_SegmentedBar_render(UI_SegmentedBar *bar) {
	if (bar->drawn) {
		return true;
	}
	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}
	const UI_SegmentedBarConfig *config = bar->config;
	switch (bar->step) {
		case 0: {
			// Draw the empty segments only on the first draw.
			uint16_t x, width, offset, side;
			UI_SegmentedBar_segmentGeometry(bar, bar->segment, &x, &width, &offset, &side);
			ST7789_DrawFilledRectangle(x, config->y + config->zero_extension,
				width, bar->segment_height, config->color_track);
			bar->segment++;
			if (bar->segment == 2 * config->segments_per_side) {
				bar->segment = 0;
				bar->step++;
			}
			break;
		}
		case 1:
			// Draw the fixed zero marker only on the first draw.
			ST7789_DrawFilledRectangle(bar->center_x, config->y, config->zero_width,
				bar->segment_height + 2 * config->zero_extension, config->color_zero);
			bar->step++;
			break;

		case 2: {
			// Labels belong to the item and remain fixed between updates.
			int16_t value = UI_SegmentedBar_labelValue(bar, bar->label);
			char text[32];
			UI_SegmentedBar_formatLabel(bar, value, text, sizeof(text));
			ST7789_TextSize size;
			ST7789_MeasureText(text, config->label_font, &size);
			ST7789_WriteString(UI_SegmentedBar_labelX(bar, value, size.width),
				config->y + config->height - Fonts[config->label_font].height,
				text, config->label_font, config->color_label, config->color_background);
			bar->label++;
			if (bar->label == bar->label_count) {
				bar->step++;
			}
			break;
		}
		case 3:
			// Skip unchanged segments; submit at most one rectangle per call.
			while (bar->segment < 2 * config->segments_per_side) {
				uint16_t segment = bar->segment;
				bar->segment++;
				uint16_t x, width, offset, side;
				UI_SegmentedBar_segmentGeometry(bar, segment, &x, &width, &offset, &side);
				uint16_t old_fill = UI_SegmentedBar_segmentFill(bar, bar->drawn_value, side, offset, width);
				uint16_t new_fill = UI_SegmentedBar_segmentFill(bar, bar->value, side, offset, width);
				if (old_fill == new_fill) {
					continue;
				}
				uint16_t small;
				uint16_t large;
				uint16_t color;
				if (new_fill > old_fill) {
					small = old_fill;
					large = new_fill;
					color = config->color_fill;
				} else {
					small = new_fill;
					large = old_fill;
					color = config->color_track;
				}
				if (side == 0) {
					x += width - large;
				} else {
					x += small;
				}
				ST7789_DrawFilledRectangle(x, config->y + config->zero_extension,
					large - small, bar->segment_height, color);
				return false;
			}
			// All submitted transfers have completed before saving the displayed value.
			bar->drawn_value = bar->value;
			bar->drawn = true;
			return true;
	}
	return false;
}

// =======================================================================
// Graph
// =======================================================================

static void UI_Trace_process(UI_Graph *graph, UI_GraphSample sample, bool usable, uint32_t now) {
	UI_Trace*	trace		= &graph->history;
	uint16_t	capacity	= graph->config.capacity;
	uint32_t	missing;
	if (trace->count == 0) {
		// Start the history only when the first usable sample is available
		trace->last_tick = now;
		if (!usable) {
			return;
		}
		missing = 1;
	} else {
		uint32_t elapsed = now - trace->last_tick;
		missing = elapsed / graph->sample_period_ms;
		if (missing == 0) {
			return;
		}
		// Advance by complete periods, preserving the remaining fraction of time
		trace->last_tick += missing * graph->sample_period_ms;

		if (!usable) {
			// Invalid data repeat the last usable value already stored in the ring
			uint16_t previous = (trace->write + capacity - 1) % capacity;
			sample = trace->samples[previous];
		}
	}

	trace->version += missing;
	// Older missed intervals cannot remain visible once the whole ring is filled
	if (missing > capacity) {
		missing = capacity;
	}
	for (uint32_t i = 0; i < missing; i++) {
		trace->samples[trace->write] = sample;
		trace->write = (trace->write + 1U) % capacity;
		if (trace->count < capacity) {
			trace->count++;
		}
	}
}

static uint16_t UI_Trace_copy(const UI_Graph *graph, UI_GraphSample *destination) {
	const UI_Trace *trace = &graph->history;
	uint16_t capacity = graph->config.capacity;
	uint16_t oldest = (trace->write + capacity - trace->count) % capacity;
	for (uint16_t i = 0; i < trace->count; i++) {
		destination[i] = trace->samples[(oldest + i) % capacity];
	}
	return trace->count;
}

static void UI_FormatGraphTime(char *text, uint32_t ms) {
	if (ms == 0) {
		snprintf(text, 16, "0s");
	} else if (ms % 1000U == 0) {
		snprintf(text, 16, "-%lus", (unsigned long)(ms / 1000U));
	} else {
		snprintf(text, 16, "-%lu.%lus", (unsigned long)(ms / 1000U),
					(unsigned long)((ms % 1000U) / 100U));
	}
}

static int32_t UI_Graph_valueY(const UI_Graph *graph, int32_t value) {
	int32_t minimum = 0;
	if (graph->config.symmetric_scale) {
		minimum = -(int32_t)graph->maximum;
	}
	if (value < minimum) {
		value = minimum;
	} else if (value > graph->maximum) {
		value = graph->maximum;
	}
	return (graph->maximum - value) * (graph->config.height - 1) /
			(graph->maximum - minimum);
}

// Position is expressed in sample intervals multiplied by the pixel width.
static int32_t UI_Graph_interpolatedY(const UI_Graph *graph, uint8_t series, uint32_t position) {
	uint32_t pixel_span = graph->config.width - 1;
	uint16_t index = position / pixel_span;
	uint32_t fraction = position % pixel_span;
	int32_t y = UI_Graph_valueY(graph, graph->snapshot[index].values[series]);
	if (fraction != 0 && index + 1 < graph->snapshot_count) {
		int32_t next_y = UI_Graph_valueY(graph, graph->snapshot[index + 1].values[series]);
		y += (next_y - y) * (int32_t)fraction / (int32_t)pixel_span;
	}
	return y;
}

static uint16_t UI_Graph_pixelColor(const void *context, uint32_t position) {
	const UI_Graph *item = context;
	const UI_GraphConfig *graph = &item->config;
	int32_t x = position % graph->width, y = position / graph->width;
	uint16_t color = graph->color_background;
	/* Five horizontal/vertical grid lines, drawn with the curves in one pass. */
	bool horizontal = false, vertical = false;
	for (int32_t i = 0; i <= 4; i++) {
		if (y == i * (graph->height - 1) / 4) {
			horizontal = true;
		}
		if (x == i * (graph->width - 1) / 4) {
			vertical = true;
		}
	}
	if ((horizontal && x % 4 < 2) || (vertical && y % 4 < 2)) {
		color = graph->color_grid;
	}

	if (item->snapshot_count == 0) {
		return color;
	}
	// Keep the newest sample at the right edge, even while history is filling.
	uint32_t pixel_span = graph->width - 1;
	uint32_t sample_span = graph->capacity - 1;
	uint32_t first_position = (graph->capacity - item->snapshot_count) * pixel_span;
	uint32_t right_position = x * sample_span;
	if (right_position < first_position) {
		return color;
	}
	uint32_t left_position = right_position;
	if (x > 0) {
		left_position = (x - 1) * sample_span;
	}
	if (left_position < first_position) {
		left_position = first_position;
	}
	left_position -= first_position;
	right_position -= first_position;
	uint8_t matching_series[GRAPH_MAX_SERIES];
	uint8_t matching_count = 0;
	for (uint8_t series = 0; series < graph->series_count; series++) {
		int32_t minimum_y = UI_Graph_interpolatedY(item, series, left_position);
		int32_t maximum_y = minimum_y;
		int32_t right_y = UI_Graph_interpolatedY(item, series, right_position);
		if (right_y < minimum_y) {
			minimum_y = right_y;
		}
		if (right_y > maximum_y) {
			maximum_y = right_y;
		}

		// Include all samples falling in this column so narrow peaks stay visible.
		uint16_t first_index = left_position / pixel_span;
		uint16_t last_index = right_position / pixel_span;
		for (uint16_t index = first_index + 1; index <= last_index; index++) {
			int32_t sample_y = UI_Graph_valueY(item, item->snapshot[index].values[series]);
			if (sample_y < minimum_y) {
				minimum_y = sample_y;
			}
			if (sample_y > maximum_y) {
				maximum_y = sample_y;
			}
		}
		if (y >= minimum_y && y <= maximum_y) {
			matching_series[matching_count] = series;
			matching_count++;
		}
	}
	if (matching_count > 0) {
		/* Coincident curves alternate colors instead of hiding series A. */
		uint8_t series = matching_series[(x / 4) % matching_count];
		color = graph->series[series].color;
	}
	return color;
}

static void UI_Graph_updateScale(UI_Graph *graph, bool first_draw, uint32_t now) {
	// Consider every sample still visible in the history window
	int32_t peak = 0;
	for (uint16_t i = 0; i < graph->history.count; i++) {
		for (uint8_t series = 0; series < graph->config.series_count; series++) {
			int32_t value = graph->history.samples[i].values[series];
			if (graph->config.symmetric_scale && value < 0) {
				value = -value;
			}
			if (value > peak) {
				peak = value;
			}
		}
	}

	// Add headroom and round upward according to the magnitude of the scale
	int32_t target = (peak * (100 + GRAPH_SCALE_MARGIN_PERCENT) + 99) / 100;
	if (target < graph->config.minimum_scale) {
		target = graph->config.minimum_scale;
	}
	int32_t rounding_step = 1;
	while (target > rounding_step * 10) {
		rounding_step *= 10;
	}
	target = (target + rounding_step - 1) / rounding_step * rounding_step;
	if (target > INT16_MAX) {
		target = INT16_MAX;
	}

	int32_t current = graph->maximum;
	if (first_draw || target > current) {
		// Expand immediately so the current samples remain visible
		current = target;
		graph->shrink_pending = false;
	} else if (target * 100 <= current * GRAPH_SCALE_SHRINK_PERCENT) {
		// Require a substantially smaller range to persist before zooming in
		if (!graph->shrink_pending) {
			graph->shrink_started_at_ms = now;
			graph->shrink_pending = true;
		} else if (now - graph->shrink_started_at_ms >= GRAPH_SCALE_SHRINK_DELAY_MS) {
			current = target;
			graph->shrink_pending = false;
		}
	} else {
		graph->shrink_pending = false;
	}

	graph->maximum = (int16_t)current;
}

static void UI_Graph_prepareLegend(UI_Graph *graph) {
	// Fit as many legends as possible on each row, then center the row
	uint8_t first = 0;
	uint16_t y = graph->config.y + graph->config.height + GRAPH_TIME_LABEL_GAP +
		Fonts[GRAPH_AXIS_FONT].height + GRAPH_LEGEND_GAP;
	while (first < graph->config.series_count) {
		uint8_t end = first;
		uint16_t width = 0;
		uint16_t entry_width[GRAPH_MAX_SERIES];
		while (end < graph->config.series_count) {
			ST7789_TextSize size;
			ST7789_MeasureText(graph->config.series[end].legend, GRAPH_LEGEND_FONT, &size);
			entry_width[end] = GRAPH_LEGEND_LINE_WIDTH + GRAPH_LEGEND_TEXT_GAP + size.width;
			if (entry_width[end] > graph->config.width) {
				Error_Handler();
			}
			uint16_t next_width = width + entry_width[end];
			if (end > first) {
				next_width += GRAPH_LEGEND_SERIES_GAP;
			}
			if (next_width > graph->config.width) {
				break;
			}
			width = next_width;
			end++;
		}

		if (y + Fonts[GRAPH_LEGEND_FONT].height > ST7789_HEIGHT) {
			Error_Handler();
		}
		uint16_t x = graph->config.x + (graph->config.width - width) / 2;
		for (uint8_t series = first; series < end; series++) {
			graph->legend_x[series] = x;
			graph->legend_y[series] = y;
			x += entry_width[series] + GRAPH_LEGEND_SERIES_GAP;
		}
		first = end;
		y += Fonts[GRAPH_LEGEND_FONT].height + GRAPH_LEGEND_GAP;
	}
}

void UI_Graph_init(UI_Graph *graph, const UI_GraphConfig *config) {
	if (config->width < 2 || config->capacity < 2 || config->capacity > GRAPH_MAX_SAMPLES ||
		config->height < 2 || config->history_ms == 0 ||
		config->minimum_scale == 0 || config->minimum_scale > INT16_MAX ||
		config->max_decimal_places > 1 || config->max_digits == 0 ||
		config->series == NULL || config->series_count < 1 || config->series_count > GRAPH_MAX_SERIES) {
		Error_Handler();
	}

	*graph = (UI_Graph){0};
	graph->config = *config;
	graph->sample_period_ms = (config->history_ms + (config->capacity - 1) / 2) / (config->capacity - 1);
	if (graph->sample_period_ms == 0) {
		Error_Handler();
	}
	graph->history.last_tick = HAL_GetTick();
}

void UI_Graph_updateHistory(UI_Graph *graph, UI_GraphSample sample, bool usable, uint32_t now) {
	UI_Trace_process(graph, sample, usable, now);
}

void UI_Graph_startRendering(UI_Graph *graph, bool first_draw) {
	uint32_t now = HAL_GetTick();
	UI_Graph_updateScale(graph, first_draw, now);

	// Use one format for every Y label, based on the largest absolute limit
	uint32_t integer_part = graph->maximum / 10;
	uint8_t integer_digits = 1;
	while (integer_part >= 10) {
		integer_part /= 10;
		integer_digits++;
	}
	graph->decimal_places = graph->config.max_decimal_places;
	if (integer_digits >= graph->config.max_digits) {
		graph->decimal_places = 0;
	} else if (graph->decimal_places > graph->config.max_digits - integer_digits) {
		graph->decimal_places = graph->config.max_digits - integer_digits;
	}

	bool scale_changed = graph->maximum != graph->drawn_maximum;
	graph->first_draw = first_draw;
	graph->drawn = false;
	graph->tick = 0;

	if (!first_draw && !scale_changed && graph->history.version == graph->drawn_version) {
		graph->drawn = true;
		return;
	}

	graph->snapshot_count = UI_Trace_copy(graph, graph->snapshot);
	graph->snapshot_version = graph->history.version;
	if (first_draw) {
		UI_Graph_prepareLegend(graph);
	}
	if (first_draw || scale_changed) {
		graph->step = 0;
	} else {
		graph->step = 2;
	}
}

bool UI_Graph_render(UI_Graph *graph) {
	if (graph->drawn) {
		return true;
	}
	if (ST7789_GetState() != ST7789_STATE_IDLE) {
		return false;
	}

	const UI_GraphConfig *plot = &graph->config;
	switch (graph->step) {
		case 0: {
			// Draw three value labels and three time labels
			char text[16];
			if (graph->tick < 3) {
				int32_t range = graph->maximum;
				if (graph->config.symmetric_scale) {
					range *= 2;
				}
				int32_t value = graph->maximum - range * graph->tick / 2;
				int32_t magnitude = value;
				if (magnitude < 0) {
					magnitude = -magnitude;
				}
				if (graph->decimal_places == 0) {
					int32_t rounded = (magnitude + 5) / 10;
					if (value < 0) {
						rounded = -rounded;
					}
					snprintf(text, sizeof(text), "%ld\xB0", (long)rounded);
				} else {
					const char *sign = "";
					if (value < 0) {
						sign = "-";
					}
					snprintf(text, sizeof(text), "%s%ld.%ld\xB0", sign, (long)(magnitude / 10), (long)(magnitude % 10));
				}
				uint16_t y = plot->y + graph->tick * (plot->height - 1) / 2 - Fonts[GRAPH_AXIS_FONT].height / 2;
				ST7789_WriteTextField(	GRAPH_AXIS_LEFT_MARGIN,
										y,
										plot->x - GRAPH_AXIS_LEFT_MARGIN - GRAPH_AXIS_GAP,
										text,
										GRAPH_AXIS_FONT,
										ST7789_TEXT_RIGHT,
										graph->config.text_color,
										plot->color_background);
			} else {
				uint8_t tick = graph->tick - 3;
				uint16_t x;
				ST7789_TextAlign align;
				if (tick == 0) {
					x = plot->x;
					align = ST7789_TEXT_LEFT;
					UI_FormatGraphTime(text, graph->config.history_ms);
				} else if (tick == 1) {
					x = plot->x + (plot->width - 1) / 2 - GRAPH_TIME_LABEL_WIDTH / 2;
					align = ST7789_TEXT_CENTER;
					UI_FormatGraphTime(text, graph->config.history_ms / 2);
				} else {
					x = plot->x + plot->width - GRAPH_TIME_LABEL_WIDTH;
					align = ST7789_TEXT_RIGHT;
					UI_FormatGraphTime(text, 0);
				}
				ST7789_WriteTextField(	x,
										plot->y + plot->height + GRAPH_TIME_LABEL_GAP,
										GRAPH_TIME_LABEL_WIDTH,
										text,
										GRAPH_AXIS_FONT,
										align,
										graph->config.text_color,
										plot->color_background);
			}
			graph->tick++;
			if (graph->tick == 6) {
				graph->tick = 0;
				if (graph->first_draw) {
					graph->step = 1;
				} else {
					graph->step = 2;
				}
			}
			return false;
		}

		case 1: {
			// Draw each legend using the layout saved at the first draw
			uint8_t series = graph->tick / 2;
			uint16_t x = graph->legend_x[series];
			uint16_t y = graph->legend_y[series];
			uint16_t color = plot->series[series].color;
			const char *text = plot->series[series].legend;
			if (graph->tick % 2 == 0) {
				ST7789_DrawFilledRectangle(	x,
											y + (Fonts[GRAPH_LEGEND_FONT].height - GRAPH_LEGEND_LINE_HEIGHT) / 2,
											GRAPH_LEGEND_LINE_WIDTH,
											GRAPH_LEGEND_LINE_HEIGHT,
											color);
			} else {
				ST7789_WriteString(	x + GRAPH_LEGEND_LINE_WIDTH + GRAPH_LEGEND_TEXT_GAP,
									y,
									text,
									GRAPH_LEGEND_FONT,
									color,
									plot->color_background);
			}
			graph->tick++;
			if (graph->tick == 2 * plot->series_count) {
				graph->step++;
			}
			return false;
		}

		case 2:
			ST7789_DrawRectanglePixels(	plot->x,
										plot->y,
										plot->width,
										plot->height,
										UI_Graph_pixelColor,
										graph);
			graph->step++;
			return false;

		default:
			graph->drawn_version = graph->snapshot_version;
			graph->drawn_maximum = graph->maximum;
			graph->drawn = true;
			return true;
	}
}
