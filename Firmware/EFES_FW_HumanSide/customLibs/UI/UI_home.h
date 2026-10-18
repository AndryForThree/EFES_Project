#ifndef UI_HOME_H
#define UI_HOME_H

#include "UI_private.h"

/* Private page renderer. Call Process only while ST7789 is IDLE, using the
 * same state snapshot until it returns true. Reset after clearing the page.
 */
void UI_Home_Reset(void);
bool UI_Home_Process(const UI_State *state);

#endif
