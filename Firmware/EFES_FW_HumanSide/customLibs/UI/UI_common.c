#include "UI_common.h"
#include "UI_private.h"
#include <stdio.h>
#include <string.h>

uint16_t UI_SensorDeviation(const Sensor_State *state) {
	int32_t difference = (int32_t)state->channel_a_angle_deci_deg - state->channel_b_angle_deci_deg;
	return (uint16_t)(difference < 0 ? -difference : difference);
}

// =======================================================================
// Common history buffers
// =======================================================================

void UI_Trace_Init(UI_Trace *trace, ST7789_GraphSample *storage,
					uint16_t capacity, uint32_t history_ms)
{
	*trace = (UI_Trace){
		.samples = storage, .capacity = capacity,
		.history_ms = history_ms, .last_tick = HAL_GetTick()
	};
}

void UI_Trace_Process(UI_Trace *trace, ST7789_GraphSample sample,
						bool usable, uint32_t now)
{
	uint32_t elapsed = now - trace->last_tick;
	if (elapsed == 0) return;
	trace->last_tick = now;

	if (usable) {
		trace->held_sample = sample;
		if (!trace->has_sample) {
			trace->has_sample = true;
			trace->phase = trace->history_ms;
		}
	}
	if (!trace->has_sample) return;

	/* Fractional sample period; repeat the last usable pair during a fault.
		* No array shifting, catch-up loop or reset when data becomes usable again.
		*/
	trace->phase += elapsed * (trace->capacity - 1U);
	if (trace->phase < trace->history_ms) return;
	trace->phase %= trace->history_ms;
	trace->samples[trace->write] = trace->held_sample;
	trace->write = (trace->write + 1U) % trace->capacity;
	if (trace->count < trace->capacity) trace->count++;
	trace->version++;
}

uint16_t UI_Trace_Copy(const UI_Trace *trace, ST7789_GraphSample *destination)
{
	uint16_t oldest = (trace->write + trace->capacity - trace->count) % trace->capacity;
	for (uint16_t i = 0; i < trace->count; i++)
		destination[i] = trace->samples[(oldest + i) % trace->capacity];
	return trace->count;
}

// =======================================================================
// Shared drawing components
// =======================================================================

#define HEADER_FONT					FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define HEADER_TEXT					UI_TEXT_COLOR
#define HEADER_BORDER				UI_BORDER_COLOR
#define HEADER_BACKGROUND			UI_BAR_BACKGROUND /* Navigation strip, distinct from data cards. */
#define HEADER_ACTIVE				UI_TITLE_COLOR
#define HEADER_INACTIVE				UI_INACTIVE_COLOR
#define MODE_TEXT_COLOR				UI_TEXT_COLOR
#define MODE_RULE_COLOR				UI_MUTED_COLOR

#define UI_FONT_MODE			FONT_RAJDHANI_BOLD_28

void UI_Header_Init(UI_Header *header, App_Page page)
{
	*header = (UI_Header){.page = page, .count = APP_PAGE_COUNT};
}

bool UI_Header_Process(UI_Header *header, const char *title)
{
	if (header->drawn && strcmp(header->title, title) == 0) return true;

	if (header->step == 0) {
		header->drawn = false;
		header->title = title;
		header->dot = 0;
	}
	ST7789_Result result = ST7789_OK;
	switch (header->step) {
		case 0:
			result = ST7789_DrawFilledRectangle(0, 0, 320, 22, HEADER_BACKGROUND);
			break;
		case 1:
			result = ST7789_DrawFilledRectangle(0, 21, 320, 1, HEADER_BORDER);
			break;
		case 2:
			result = ST7789_WriteString(8, 3, header->title, HEADER_FONT,
										HEADER_TEXT, HEADER_BACKGROUND);
			break;
		case 3:
			result = ST7789_DrawFilledCircle(310 - (header->count - 1 - header->dot) * 10,
						11, 2, header->dot == header->page ? HEADER_ACTIVE : HEADER_INACTIVE,
						HEADER_BACKGROUND);
			if (result == ST7789_OK && ++header->dot == header->count) header->step++;
			return false;
		default:
			header->drawn = true;
			header->step = 0;
			return true;
	}
	if (result == ST7789_OK) header->step++;
	return false;
}

static const struct {
	const char *text;
	uint16_t color;
} modes[] = {
	[APP_DRIVE_NORMAL] = {"COMFORT", UI_MODE_COMFORT_COLOR},
	[APP_DRIVE_ECO] = {"ECO", UI_MODE_ECO_COLOR},
	[APP_DRIVE_SPORT] = {"SPORT", UI_MODE_SPORT_COLOR}
};

void UI_Mode_Init(UI_Mode *mode_bar)
{
	*mode_bar = (UI_Mode){0};
}

bool UI_Mode_Process(UI_Mode *mode_bar, App_DriveMode mode)
{
	if (mode_bar->drawn && mode_bar->mode == mode) return true;
	ST7789_Result result = ST7789_OK;
	uint16_t color = modes[mode].color;
	switch (mode_bar->step) {
		case 0: {
			mode_bar->drawn = false;
			ST7789_TextSize size;
			ST7789_MeasureText(modes[mode].text, UI_FONT_MODE, &size);
			uint16_t icon_width = Assets[ASSET_DRIVE_MODE].width;
			mode_bar->symbol_x = (320 - icon_width - 17 - size.width) / 2;
			mode_bar->text_x = mode_bar->symbol_x + icon_width + 17;
			result = ST7789_DrawRoundedRectangle(3, 205, 314, 31, 5,
													color, color, UI_BACKGROUND);
			break;
		}
		case 1:
			result = ST7789_DrawAsset(mode_bar->symbol_x, 208, ASSET_DRIVE_MODE, 0, color);
			break;
		case 2:
			result = ST7789_DrawFilledRectangle(mode_bar->text_x - 9, 210, 1, 21, MODE_RULE_COLOR);
			break;
		case 3:
			result = ST7789_WriteString(mode_bar->text_x, 208, modes[mode].text, UI_FONT_MODE,
										MODE_TEXT_COLOR, color);
			break;
		default:
			mode_bar->drawn = true;
			mode_bar->mode = mode;
			mode_bar->step = 0;
			return true;
	}
	if (result == ST7789_OK) mode_bar->step++;
	return false;
}

void UI_FormatGraphTime(char *text, uint32_t ms)
{
	if (ms == 0) snprintf(text, 16, "0s");
	else if (ms % 1000U == 0) snprintf(text, 16, "-%lus", (unsigned long)(ms / 1000U));
	else snprintf(text, 16, "-%lu.%lus", (unsigned long)(ms / 1000U),
					(unsigned long)((ms % 1000U) / 100U));
}

void UI_Developer_Init(UI_Developer *developer)
{
	*developer = (UI_Developer){0};
}

bool UI_Developer_Process(UI_Developer *developer, bool enabled, uint32_t elapsed_ms)
{
	/* The field accepted on the previous call has now finished transferring. */
	if (developer->step == 1) {
		developer->step = 0;
		return true;
	}
	if (!enabled && !developer->drawn) return true;
	if (enabled && developer->drawn && developer->elapsed_ms == elapsed_ms) return true;

	char text[32] = "";
	if (enabled) {
		snprintf(text, sizeof(text), "Rend.: %lu ms", (unsigned long)elapsed_ms);
	}
	/* A small field in the header's free area leaves title and dots untouched.
	 * The driver copies the local text before returning.
	 */
	if (ST7789_WriteTextField(132, 5, 96, text,
		FONT_BARLOW_SEMI_CONDENSED_BOLD_10, ST7789_TEXT_CENTER,
		UI_MUTED_COLOR, HEADER_BACKGROUND) != ST7789_OK) return false;

	developer->drawn = enabled;
	developer->elapsed_ms = elapsed_ms;
	developer->step = 1;
	return false;
}
