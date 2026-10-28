#ifndef UI_PRIVATE_H
#define UI_PRIVATE_H

#include "UI_module.h"
#include "App.h"
#include "st7789.h"

// =======================================================================
// Theme
// =======================================================================

#define UI_BACKGROUND			0x0022U
#define UI_CARD_BACKGROUND		0x0884U
#define UI_BORDER_COLOR			0x21ACU
#define UI_SELECTION_COLOR		0x19CEU
#define UI_ACCENT_COLOR			0x36BFU
#define UI_TEXT_COLOR			0xF7DFU
#define UI_MUTED_COLOR			0x8D59U

#define UI_TITLE_COLOR			0x3DFFU
#define UI_OK_COLOR				0x07D0U
#define UI_WARNING_COLOR		0xFE60U
#define UI_MODE_COMFORT_COLOR	0x3934U
#define UI_MODE_ECO_COLOR		0x032CU
#define UI_MODE_SPORT_COLOR		0xB984U
#define UI_TRACK_COLOR			0x2A4AU

#define UI_ERROR_COLOR			0xF800U
#define UI_TEAL_COLOR			0x06D8U
#define UI_YELLOW_COLOR			0xFFE0U
#define UI_MAGENTA_COLOR		0xF81FU
#define UI_BAR_BACKGROUND		0x0043U
#define UI_INACTIVE_COLOR		0x426CU

// =======================================================================
// Graph configuration
// =======================================================================

#define GRAPH_WIDTH_PX			264					
#define GRAPH_HISTORY_MS		10000				// Total time window rapresented by the graph	
#define GRAPH_REFRESH_MS		100					// Refresh period of the graph
#define GRAPH_DEVIATION_SCALE	2					// 
#define GRAPH_SAMPLES			GRAPH_WIDTH_PX		// 
#define GRAPH_SAMPLE_US			((GRAPH_HISTORY_MS * 1000UL) / (GRAPH_SAMPLES - 1U))

#define STEERING_GRAPH_WIDTH_PX		264
#define STEERING_GRAPH_HISTORY_MS	10000
#define STEERING_GRAPH_REFRESH_MS	100
#define STEERING_GRAPH_MIN_ANGLE	(-450) /* Road wheel angle, tenths of a degree. */
#define STEERING_GRAPH_MAX_ANGLE	450
#define STEERING_GRAPH_SAMPLES		STEERING_GRAPH_WIDTH_PX


// =======================================================================
// Shared components
// =======================================================================



/* Presentation value shared by Home, Sensor and the history graph. */
uint16_t UI_SensorDeviation(const Sensor_State *state);

// Common Page header
void UI_Header_Reset	(const char *title, uint8_t page, uint8_t count);
bool UI_Header_Process	(void);

/* Shared bottom bar. Reset on page entry; process only when mode changes. */
void UI_Mode_Reset		(void);
bool UI_Mode_Process	(App_DriveMode mode);

/* Independent of page navigation and display transfers. Main context only. */
uint32_t UI_SensorHistory_Version(void);
uint16_t UI_SensorHistory_Copy(ST7789_GraphSample *destination);

enum { 
	FEEDBACK_LIVE, 
	FEEDBACK_STALE, 
	FEEDBACK_FAULT 
};
uint32_t UI_SteeringHistory_Version(void);
uint16_t UI_SteeringHistory_Copy(ST7789_GraphSample *destination);

/* The caller provides a persistent buffer of at least 16 bytes. */
void UI_FormatGraphTime(char *text, uint32_t ms);

#endif
