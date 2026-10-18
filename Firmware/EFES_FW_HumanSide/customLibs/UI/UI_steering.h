#ifndef UI_STEERING_H
#define UI_STEERING_H

#include "UI_private.h"

#define STEERING_GRAPH_WIDTH_PX 264U
#define STEERING_GRAPH_HISTORY_MS 10000U
#define STEERING_GRAPH_REFRESH_MS 100U
#define STEERING_GRAPH_MIN_ANGLE (-450) /* Road wheel angle, tenths of a degree. */
#define STEERING_GRAPH_MAX_ANGLE 450
#define STEERING_GRAPH_SAMPLES STEERING_GRAPH_WIDTH_PX
#define STEERING_FEEDBACK_STALE_MS 1000U

void UI_Steering_Init(void);
void UI_Steering_Sample(const UI_State *state, uint32_t now);
void UI_Steering_Reset(void);
bool UI_Steering_Process(const UI_State *state);

#endif
