#ifndef UI_HISTORY_H
#define UI_HISTORY_H

#include "UI_private.h"
#include "st7789.h"

#define GRAPH_WIDTH_PX 264U
#define GRAPH_HISTORY_MS 10000U
#define GRAPH_REFRESH_MS 100U
#define GRAPH_DEVIATION_SCALE 2U /* Y range: zero to twice the configured FPGA limit. */
#define GRAPH_SAMPLES GRAPH_WIDTH_PX
#define GRAPH_SAMPLE_US ((GRAPH_HISTORY_MS * 1000UL) / (GRAPH_SAMPLES - 1U))

/* Independent of page navigation and display transfers. Main context only. */
void UI_History_Init(void);
void UI_History_Process(const UI_State *state, uint32_t now);
uint32_t UI_History_Version(void);
uint16_t UI_History_Copy(ST7789_GraphSample *destination);

#endif
