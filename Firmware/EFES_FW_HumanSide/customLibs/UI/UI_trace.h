#ifndef UI_TRACE_H
#define UI_TRACE_H

#include "st7789.h"
#include <stdbool.h>

/* Private shared ring for two signals. Storage is owned by the caller. */
typedef struct {
    ST7789_GraphSample *samples;
    ST7789_GraphSample held_sample;
    uint16_t capacity, write, count;
    uint32_t history_ms, last_tick, phase, version;
    bool has_sample;
} UI_Trace;

void UI_Trace_Init(UI_Trace *trace, ST7789_GraphSample *storage,
                   uint16_t capacity, uint32_t history_ms);
void UI_Trace_Process(UI_Trace *trace, ST7789_GraphSample sample,
                      bool usable, uint32_t now);
uint16_t UI_Trace_Copy(const UI_Trace *trace, ST7789_GraphSample *destination);

#endif
