#ifndef UI_HOME_H
#define UI_HOME_H

#include "UI_private.h"

/* Init assigns the page identity once. Process runs every loop: history uses
 * current data, while drawing uses a private stable snapshot. Leaving the page
 * prepares a full redraw for the next entry without clearing its history.
 * draw grants display access; true means the complete render has finished.
 */
void UI_Home_Init(App_Page page);
bool UI_Home_Process(const App_View *current, bool draw);

#endif
