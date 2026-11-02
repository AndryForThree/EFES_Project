#ifndef UI_STEERING_H
#define UI_STEERING_H

#include "UI_private.h"

// =======================================================================
// Page customization
// =======================================================================

#define STEERING_FAULT_COLOR			UI_ERROR_COLOR
#define STEERING_TITLE					UI_TITLE_COLOR
#define STEERING_BORDER					UI_BORDER_COLOR
#define STEERING_REQUESTED_COLOR		UI_YELLOW_COLOR /* Bright yellow. */
#define STEERING_ACTUAL_COLOR			UI_MAGENTA_COLOR /* Bright magenta. */
#define STEERING_LIVE_COLOR				UI_OK_COLOR
#define STEERING_STALE_COLOR			UI_WARNING_COLOR

#define STEERING_FONT_TITLE				FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define STEERING_FONT_VALUE				FONT_RAJDHANI_BOLD_28
#define STEERING_FONT_LABEL				FONT_INTER_MEDIUM_10
#define STEERING_FONT_STATUS			FONT_BARLOW_SEMI_CONDENSED_BOLD_12
#define STEERING_GRAPH_X				45U
#define STEERING_GRAPH_Y				111U
#define STEERING_GRAPH_HEIGHT_PX		58U

#define STEERING_GRAPH_WIDTH_PX			264
#define STEERING_GRAPH_CAPACITY			264
#define STEERING_GRAPH_HISTORY_MS		10000
#define STEERING_GRAPH_MINIMUM_SCALE	10 /* Road wheel angle, tenths of a degree. */

// Graph presentation
#define STEERING_GRAPH_BACKGROUND_COLOR	UI_CARD_BACKGROUND
#define STEERING_GRAPH_MAX_DIGITS			3
#define STEERING_GRAPH_MAX_DECIMAL_PLACES	1
#define STEERING_GRAPH_SYMMETRIC_SCALE	true
#define STEERING_GRAPH_LEGEND_A			"REQUESTED"
#define STEERING_GRAPH_LEGEND_B			"ACTUAL"

/* Init assigns the page identity once. Process runs every loop: history uses
 * current data, while drawing uses a private stable snapshot. Leaving the page
 * prepares a full redraw for the next entry without clearing its history.
 * draw grants display access; true means the complete render has finished.
 */
void UI_Steering_Init(App_Page page);
bool UI_Steering_Process(const App_View *current, bool draw);

#endif
