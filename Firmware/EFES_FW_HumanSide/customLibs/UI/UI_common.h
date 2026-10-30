#ifndef UI_COMMON_H
#define UI_COMMON_H

#include "App.h"
#include "st7789.h"

// =======================================================================
// Shared components
// =======================================================================

uint16_t UI_SensorDeviation(const Sensor_State *state);



/* Runtime state belongs to the page using each component. */
typedef struct {
	bool drawn;
	const char *title;
	App_Page page;
	uint8_t count, step, dot;
} UI_Header;

void UI_Header_Init		(UI_Header *header, App_Page page);
bool UI_Header_Process	(UI_Header *header, const char *title);



typedef struct {
	bool drawn;
	App_DriveMode mode;
	uint8_t step;
	uint16_t symbol_x, text_x;
} UI_Mode;

void UI_Mode_Init		(UI_Mode *mode_bar);
bool UI_Mode_Process	(UI_Mode *mode_bar, App_DriveMode mode);



typedef struct {
	bool drawn;
	uint8_t step;
	uint32_t elapsed_ms;
} UI_Developer;

void UI_Developer_Init		(UI_Developer *developer);
bool UI_Developer_Process	(UI_Developer *developer, bool enabled, uint32_t elapsed_ms);



typedef struct {
	ST7789_GraphSample *samples;
	ST7789_GraphSample held_sample;
	uint16_t capacity, write, count;
	uint32_t history_ms, last_tick, phase, version;
	bool has_sample;
} UI_Trace;

void		UI_Trace_Init(UI_Trace *trace, ST7789_GraphSample *storage, uint16_t capacity, uint32_t history_ms);
void		UI_Trace_Process(UI_Trace *trace, ST7789_GraphSample sample, bool usable, uint32_t now);
uint16_t	UI_Trace_Copy(const UI_Trace *trace, ST7789_GraphSample *destination);

void 		UI_FormatGraphTime(char *text, uint32_t ms);

#endif
