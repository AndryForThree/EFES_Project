#ifndef UI_MODE_H
#define UI_MODE_H

#include "UI_module.h"

#define UI_FONT_MODE FONT_RAJDHANI_BOLD_28

/* Shared bottom bar. Reset on page entry; process only when mode changes. */
void UI_Mode_Reset(void);
bool UI_Mode_Process(UI_DriveMode mode);

#endif
