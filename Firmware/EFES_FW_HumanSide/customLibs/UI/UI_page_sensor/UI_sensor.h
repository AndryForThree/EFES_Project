#ifndef UI_SENSOR_H
#define UI_SENSOR_H

#include "UI_private.h"

// =======================================================================
// Page customization
// =======================================================================

#define SENSOR_TEXT						UI_TEXT_COLOR
#define SENSOR_TITLE					UI_TITLE_COLOR
#define SENSOR_BORDER					UI_BORDER_COLOR
#define SENSOR_NORMAL					UI_OK_COLOR
#define SENSOR_FAULT					UI_ERROR_COLOR
#define SENSOR_STALE					UI_WARNING_COLOR
#define SENSOR_TRACK					UI_TRACK_COLOR
#define SENSOR_GRAPH_COLOR				UI_TEAL_COLOR

#define SENSOR_FONT_TITLE				FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define SENSOR_FONT_ANGLE				FONT_RAJDHANI_BOLD_40
#define SENSOR_FONT_VALUE				FONT_RAJDHANI_BOLD_42
#define SENSOR_FONT_NA					FONT_RAJDHANI_BOLD_28
#define SENSOR_FONT_HISTORY				FONT_BARLOW_SEMI_CONDENSED_BOLD_12
#define SENSOR_FONT_UPDATE				FONT_BARLOW_SEMI_CONDENSED_BOLD_10
#define SENSOR_FONT_UNIT				FONT_INTER_MEDIUM_10

#define SENSOR_DEVIATION_BAR_X			12
#define SENSOR_DEVIATION_BAR_Y			114
#define SENSOR_DEVIATION_BAR_WIDTH		156
#define SENSOR_DEVIATION_BAR_HEIGHT		8
#define SENSOR_GRAPH_X					41U
#define SENSOR_GRAPH_Y					162U
#define SENSOR_GRAPH_HEIGHT_PX			46U

#define SENSOR_GRAPH_WIDTH_PX			264
#define SENSOR_GRAPH_CAPACITY			264
#define SENSOR_GRAPH_HISTORY_MS			10000				// Total time window rapresented by the graph
#define SENSOR_GRAPH_MINIMUM_SCALE		5					// Minimum upper limit: 0.5 degrees

// Graph presentation
#define SENSOR_GRAPH_BACKGROUND_COLOR	UI_CARD_BACKGROUND
#define SENSOR_GRAPH_MAX_DIGITS				3
#define SENSOR_GRAPH_MAX_DECIMAL_PLACES		1
#define SENSOR_GRAPH_SYMMETRIC_SCALE	false
#define SENSOR_GRAPH_LEGEND				"DEVIATION"

/* Init assigns the page identity once. Process runs every loop: history uses
 * current data, while drawing uses a private stable snapshot. Leaving the page
 * prepares a full redraw for the next entry without clearing its history.
 * draw grants display access; true means the complete render has finished.
 */
void UI_Sensor_Init(App_Page page);
bool UI_Sensor_Process(const App_View *current, bool draw);

#endif
