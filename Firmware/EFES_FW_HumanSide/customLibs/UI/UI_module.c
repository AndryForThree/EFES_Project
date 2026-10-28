#include "main.h"
#include "UI_module.h"
#include "UI_private.h"
#include "App.h"
#include "tim.h"
#include "UI_home.h"
#include "UI_sensor.h"
#include "UI_steering.h"
#include "UI_settings.h"
#include "st7789.h"
#include <stdio.h>

static const char *const page_titles[APP_PAGE_COUNT] = {
	"HOME", "SENSOR DIAGNOSTICS", "STEERING RESPONSE", "SETTINGS"
};

typedef enum {
	RENDER_IDLE,
	RENDER_CLEAR,
	RENDER_HEADER,
	RENDER_PAGE,
	RENDER_TIME
} UI_RenderPhase;

typedef struct {
	App_View		render_view;
	App_Page		active_page;
	bool			alarm_active;
	UI_RenderPhase	phase;
	volatile bool	refresh_pending;
	uint16_t		refresh_period_ms;
	uint32_t		render_started_at_ms;
	uint32_t		render_elapsed_ms;
	bool			render_time_visible;
	char			render_time_text[32];
} UI_Context;

static UI_Context ui;

uint16_t UI_SensorDeviation(const Sensor_State *state)
{
	int32_t difference = (int32_t)state->channel_a_angle_deci_deg - state->channel_b_angle_deci_deg;
	return (uint16_t)(difference < 0 ? -difference : difference);
}

// =======================================================================
// Common history buffers
// =======================================================================

/* Private shared ring for two signals. Storage is owned by the caller. */
typedef struct {
	ST7789_GraphSample *samples;
	ST7789_GraphSample held_sample;
	uint16_t capacity, write, count;
	uint32_t history_ms, last_tick, phase, version;
	bool has_sample;
} UI_Trace;

static void UI_Trace_Init(UI_Trace *trace, ST7789_GraphSample *storage,
					uint16_t capacity, uint32_t history_ms)
{
	*trace = (UI_Trace){
		.samples = storage, .capacity = capacity,
		.history_ms = history_ms, .last_tick = HAL_GetTick()
	};
}

static void UI_Trace_Process(UI_Trace *trace, ST7789_GraphSample sample,
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

static uint16_t UI_Trace_Copy(const UI_Trace *trace, ST7789_GraphSample *destination)
{
	uint16_t oldest = (trace->write + trace->capacity - trace->count) % trace->capacity;
	for (uint16_t i = 0; i < trace->count; i++)
		destination[i] = trace->samples[(oldest + i) % trace->capacity];
	return trace->count;
}

static ST7789_GraphSample sensor_samples[GRAPH_SAMPLES];
static UI_Trace sensor_history;

static void UI_SensorHistory_Init(void)
{
	UI_Trace_Init(&sensor_history, sensor_samples, GRAPH_SAMPLES, GRAPH_HISTORY_MS);
}

static void UI_SensorHistory_Process(const App_View *state, uint32_t now)
{
	uint16_t deviation = UI_SensorDeviation(&state->sensor);
	bool usable = state->sensor.channel_a_valid && state->sensor.channel_b_valid &&
					!state->sensor.plausibility_fault && !state->sensor.stale;
	UI_Trace_Process(&sensor_history, (ST7789_GraphSample){
		deviation > INT16_MAX ? INT16_MAX : (int16_t)deviation,
		0
	}, usable, now);
}

uint32_t UI_SensorHistory_Version(void)
{
	return sensor_history.version;
}

uint16_t UI_SensorHistory_Copy(ST7789_GraphSample *destination)
{
	return UI_Trace_Copy(&sensor_history, destination);
}

static UI_Trace steering_history;
static ST7789_GraphSample steering_samples[STEERING_GRAPH_SAMPLES];


static void UI_SteeringHistory_Init(void)
{
	UI_Trace_Init(&steering_history, steering_samples, STEERING_GRAPH_SAMPLES, STEERING_GRAPH_HISTORY_MS);
}

static void UI_SteeringHistory_Process(const App_View *state, uint32_t now)
{
	UI_Trace_Process(&steering_history, (ST7789_GraphSample){
		state->operating.road_requested_angle_deci_deg, state->road.actual_angle_deci_deg
	}, state->operating.can_online && state->road.valid && !state->road.stale, now);
}

uint32_t UI_SteeringHistory_Version(void)
{
	return steering_history.version;
}

uint16_t UI_SteeringHistory_Copy(ST7789_GraphSample *destination)
{
	return UI_Trace_Copy(&steering_history, destination);
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

static struct {
	const char *title;
	uint8_t page, count, step, dot;
} header;

void UI_Header_Reset(const char *title, uint8_t page, uint8_t count)
{
	header.title = title;
	header.page = page;
	header.count = count;
	header.step = 0;
	header.dot = 0;
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

static const struct {
	const char *text;
	uint16_t color;
} modes[] = {
	[APP_DRIVE_NORMAL] = {"COMFORT", UI_MODE_COMFORT_COLOR},
	[APP_DRIVE_ECO] = {"ECO", UI_MODE_ECO_COLOR},
	[APP_DRIVE_SPORT] = {"SPORT", UI_MODE_SPORT_COLOR}
};

static struct {
	uint8_t step;
	uint16_t symbol_x;
	uint16_t text_x;
} mode_bar;

void UI_Mode_Reset(void)
{
	mode_bar.step = 0;
}

bool UI_Mode_Process(App_DriveMode mode)
{
	ST7789_Result result = ST7789_OK;
	uint16_t color = modes[mode].color;
	switch (mode_bar.step) {
		case 0: {
			ST7789_TextSize size;
			ST7789_MeasureText(modes[mode].text, UI_FONT_MODE, &size);
			uint16_t icon_width = Assets[ASSET_DRIVE_MODE].width;
			mode_bar.symbol_x = (320 - icon_width - 17 - size.width) / 2;
			mode_bar.text_x = mode_bar.symbol_x + icon_width + 17;
			result = ST7789_DrawRoundedRectangle(3, 205, 314, 31, 5,
													color, color, UI_BACKGROUND);
			break;
		}
		case 1:
			result = ST7789_DrawAsset(mode_bar.symbol_x, 208, ASSET_DRIVE_MODE, 0, color);
			break;
		case 2:
			result = ST7789_DrawFilledRectangle(mode_bar.text_x - 9, 210, 1, 21, MODE_RULE_COLOR);
			break;
		case 3:
			result = ST7789_WriteString(mode_bar.text_x, 208, modes[mode].text, UI_FONT_MODE,
										MODE_TEXT_COLOR, color);
			break;
		default:
			mode_bar.step = 0;
			return true;
	}
	if (result == ST7789_OK) mode_bar.step++;
	return false;
}

void UI_FormatGraphTime(char *text, uint32_t ms)
{
	if (ms == 0) snprintf(text, 16, "0s");
	else if (ms % 1000U == 0) snprintf(text, 16, "-%lus", (unsigned long)(ms / 1000U));
	else snprintf(text, 16, "-%lu.%lus", (unsigned long)(ms / 1000U),
					(unsigned long)((ms % 1000U) / 100U));
}

// =======================================================================
// UI coordination and refresh timer
// =======================================================================


/* Page functions will draw from ui.render_view, which stays unchanged
	* until the whole refresh completes. Each call performs one small step
	* and returns true only when the page refresh is finished.
	*/
static bool AlarmPage_Process(void)
{
	/* Alarm presentation will be defined with the page layout. */
	return true;
}

void UI_Init(void)
{
	ui				= (UI_Context){0};
	ui.active_page	= APP_PAGE_HOME;
	ui.phase		= RENDER_CLEAR;

	UI_SensorHistory_Init();
	UI_SteeringHistory_Init();
	ui.refresh_period_ms = APP_REFRESH_DEFAULT_MS;
	__HAL_TIM_CLEAR_FLAG(&htim6, TIM_FLAG_UPDATE);
	HAL_NVIC_ClearPendingIRQ(TIM6_DAC_IRQn);
	if (HAL_TIM_Base_Start_IT(&htim6) != HAL_OK) {
		Error_Handler();
	}
}

bool UI_SetRefreshPeriod(uint16_t period_ms)
{
	/* CubeMX initializes TIM6 with a 10 kHz counter: each millisecond is
		* 10 ticks. ARR counts from zero, so a period needs period_ms * 10 - 1.
		* The 16-bit counter supports whole-millisecond periods up to 6553 ms.
		* Validate before changing hardware; call only from the main context.
		*/
	if (period_ms == 0 || period_ms > 6553U) return false;

	/* Preserve the running state and prevent the timer ISR from observing
		* a partially updated configuration. This does not stop an active draw.
		*/
	uint32_t mask = lock();
	bool running = (htim6.Instance->CR1 & TIM_CR1_CEN) != 0;
	if (HAL_TIM_Base_Stop_IT(&htim6) != HAL_OK) {
		unlock(mask);
		return false;
	}

	/* Preload is disabled in CubeMX, so ARR takes effect immediately.
		* Restart from zero and clear the old timeout: the next interrupt must
		* occur after one complete new period. PSC and NVIC priority stay as
		* configured by CubeMX; no software update event is generated here.
		*/
	__HAL_TIM_SET_AUTORELOAD(&htim6, (uint32_t)period_ms * 10U - 1U);
	__HAL_TIM_SET_COUNTER(&htim6, 0);
	__HAL_TIM_CLEAR_FLAG(&htim6, TIM_FLAG_UPDATE);
	HAL_NVIC_ClearPendingIRQ(TIM6_DAC_IRQn);

	HAL_StatusTypeDef result = HAL_OK;
	if (running) result = HAL_TIM_Base_Start_IT(&htim6);
	unlock(mask);
	return result == HAL_OK;
}


void UI_RequestRefreshISR(void)
{
	ui.refresh_pending = true;
}

bool UI_NeedsProcess(void)
{
	return ST7789_GetState() == ST7789_STATE_IDLE &&
		(ui.phase != RENDER_IDLE || ui.refresh_pending);
}

void UI_Process(void) {
	App_View view;
	App_GetView(&view);
	if (view.UI_refresh_period_ms != ui.refresh_period_ms) {
		if (!UI_SetRefreshPeriod(view.UI_refresh_period_ms)) {
			Error_Handler();
			return;
		}
		ui.refresh_period_ms = view.UI_refresh_period_ms;
		ui.refresh_pending = true;
	}
	bool requested_alarm = view.operating.alarms != 0;

	/* History runs even when Home is selected or the driver is transferring. */
	uint32_t now = HAL_GetTick();
	UI_SensorHistory_Process(&view, now);
	UI_SteeringHistory_Process(&view, now);

	/* Never wait for the driver or change buffers used by an active draw.
		* A driver error also stops rendering here, without automatic retries.
		*/
	if (ST7789_GetState() != ST7789_STATE_IDLE) return;

	if (view.page != ui.active_page || requested_alarm != ui.alarm_active) {
		ui.active_page = view.page;
		ui.alarm_active = requested_alarm;
		ui.phase = RENDER_CLEAR;
	}

	switch (ui.phase) {
		case RENDER_IDLE: {
			/* Consume the request atomically. An interrupt after this section
			 * remains pending for the next refresh, including during a draw.
			 */
			uint32_t mask = lock();
			bool requested = ui.refresh_pending;
			ui.refresh_pending = false;
			unlock(mask);
			if (!requested) return;
			ui.render_view = view;
			ui.render_started_at_ms = HAL_GetTick();

			ui.phase = RENDER_PAGE;
			break;
		}

		case RENDER_CLEAR:
			ui.render_view = view;
			ui.render_started_at_ms = HAL_GetTick();

			if (ST7789_Fill_Color(UI_BACKGROUND) == ST7789_OK) {
				ui.render_time_visible = false;
				UI_Home_Reset();
				UI_Sensor_Reset();
				UI_Steering_Reset();
				UI_Mode_Reset();
				UI_Settings_Reset();
				if (!ui.alarm_active) {
					UI_Header_Reset(page_titles[ui.active_page], ui.active_page + 1, APP_PAGE_COUNT);
					ui.phase = RENDER_HEADER;
				} else {
					ui.phase = RENDER_PAGE;
				}
			}
			break;

		case RENDER_HEADER:
			if (UI_Header_Process()) ui.phase = RENDER_PAGE;
			break;

		case RENDER_PAGE: {
			bool finished;
			if (ui.alarm_active) {
				finished = AlarmPage_Process();
			} else if (ui.active_page == APP_PAGE_SENSOR) {
				finished = UI_Sensor_Process(&ui.render_view);
			} else if (ui.active_page == APP_PAGE_STEERING) {
				finished = UI_Steering_Process(&ui.render_view);
			} else if (ui.active_page == APP_PAGE_SETTINGS) {
				finished = UI_Settings_Process(&ui.render_view);
			} else {
				finished = UI_Home_Process(&ui.render_view);
			}
			if (finished) ui.phase = RENDER_TIME;
			break;
		}

		case RENDER_TIME:
			/* The driver is idle: the page's last transfer has completed.
			 * Measure elapsed wall time, excluding the diagnostic text below.
			 */
			ui.render_elapsed_ms = HAL_GetTick() - ui.render_started_at_ms;
			if (ui.alarm_active || (!ui.render_view.developer_mode && !ui.render_time_visible)) {
				ui.phase = RENDER_IDLE;
				break;
			}
			ui.render_time_text[0] = '\0';
			if (ui.render_view.developer_mode) {
				snprintf(ui.render_time_text, sizeof(ui.render_time_text), "Rend.: %lu ms",
					(unsigned long)ui.render_elapsed_ms);
			}
			/* A small field in the header's free area leaves title and dots untouched.
			 * The persistent text buffer remains unchanged until DMA completes.
			 */
			if (ST7789_WriteTextField(132, 5, 96, ui.render_time_text,
				FONT_BARLOW_SEMI_CONDENSED_BOLD_10, ST7789_TEXT_CENTER,
				UI_MUTED_COLOR, HEADER_BACKGROUND) == ST7789_OK) {
				ui.render_time_visible = ui.render_view.developer_mode != 0;
				ui.phase = RENDER_IDLE;
			}
			break;
	}
}
