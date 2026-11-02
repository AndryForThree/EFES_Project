#ifndef UI_HOME_H
#define UI_HOME_H

#include "UI_private.h"

// =======================================================================
// Page customization
// =======================================================================

#define HOME_TEXT_COLOR				UI_TEXT_COLOR
#define HOME_TITLE_COLOR			UI_TITLE_COLOR /* Saturated sky blue, RGB565. */
#define HOME_CARD_SYMBOL_COLOR		UI_WARNING_COLOR /* Warm yellow, RGB565. */
#define HOME_MUTED_COLOR			UI_MUTED_COLOR
#define HOME_BORDER_COLOR			UI_BORDER_COLOR
#define HOME_STATUS_OK_COLOR		UI_OK_COLOR
#define HOME_STATUS_ERROR_COLOR		UI_ERROR_COLOR
#define HOME_TRACK_COLOR			UI_TRACK_COLOR

/* Font choices by role. Sizes/positions below are expressed in pixels. */
#define HOME_FONT_CARD_TITLE		FONT_BARLOW_SEMI_CONDENSED_BOLD_16
#define HOME_FONT_TITLE				FONT_BARLOW_SEMI_CONDENSED_BOLD_16
#define HOME_FONT_NUMBER			FONT_RAJDHANI_SEMIBOLD_28
#define HOME_FONT_ANGLE				FONT_RAJDHANI_BOLD_42
#define HOME_FONT_STATUS			FONT_BARLOW_SEMI_CONDENSED_BOLD_14
#define HOME_FONT_LABEL				FONT_INTER_MEDIUM_10
#define HOME_FONT_DIRECTION			FONT_INTER_MEDIUM_12

#define HOME_WHEEL_ASSET			ASSET_STEERING_WHEEL

#define HOME_BAR_CENTER_X			220
#define HOME_BAR_SEGMENT_WIDTH		20
#define HOME_BAR_SEGMENT_PITCH		22
#define HOME_BAR_SEGMENTS_PER_SIDE	4
#define HOME_BAR_Y					125
#define HOME_BAR_HEIGHT				8
#define HOME_BAR_FULL_SCALE			4500 /* +/-450 degrees, expressed in tenths. */

/* Init assigns the page identity once. Process runs every loop: history uses
 * current data, while drawing uses a private stable snapshot. Leaving the page
 * prepares a full redraw for the next entry without clearing its history.
 * draw grants display access; true means the complete render has finished.
 */
void UI_Home_Init(App_Page page);
bool UI_Home_Process(const App_View *current, bool draw);

#endif
