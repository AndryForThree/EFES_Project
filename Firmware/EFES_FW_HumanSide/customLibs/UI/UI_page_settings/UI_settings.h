#ifndef UI_SETTINGS_H
#define UI_SETTINGS_H

#include "UI_private.h"

// =======================================================================
// Page customization
// =======================================================================

#define SETTINGS_VISIBLE_ITEMS	4U
#define SETTINGS_ROW_HEIGHT		34U

/* Init assigns the page identity once. Process runs every loop: history uses
 * current data, while drawing uses a private stable snapshot. Leaving the page
 * prepares a full redraw for the next entry without clearing its history.
 * draw grants display access; true means the complete render has finished.
 */
void UI_Settings_Init(App_Page page);
bool UI_Settings_Process(const App_View *current, bool draw);

#endif
