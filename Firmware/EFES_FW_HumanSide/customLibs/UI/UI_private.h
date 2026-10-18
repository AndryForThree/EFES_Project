#ifndef UI_PRIVATE_H
#define UI_PRIVATE_H

#include "UI_module.h"

#define UI_BACKGROUND      0x0022U
#define UI_CARD_BACKGROUND 0x0884U
#define UI_SENSOR_STALE_MS 1000U

/* Presentation only: the plausibility verdict always comes from the sensor. */
uint16_t UI_SensorDeviation(const UI_State *state);
bool UI_SensorStale(const UI_State *state, uint32_t now);

#endif
