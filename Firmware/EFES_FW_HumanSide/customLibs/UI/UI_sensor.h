#ifndef UI_SENSOR_H
#define UI_SENSOR_H

#include "UI_private.h"

/* Private renderer: same state snapshot until complete, driver IDLE on entry. */
void UI_Sensor_Reset(void);
bool UI_Sensor_Process(const UI_State *state);

#endif
