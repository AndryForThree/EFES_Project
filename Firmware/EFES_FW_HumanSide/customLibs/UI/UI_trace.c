#include "UI_trace.h"

void UI_Trace_Init(UI_Trace *trace, ST7789_GraphSample *storage,
                   uint16_t capacity, uint32_t history_ms)
{
    *trace = (UI_Trace){
        .samples = storage, .capacity = capacity,
        .history_ms = history_ms, .last_tick = HAL_GetTick()
    };
}

void UI_Trace_Process(UI_Trace *trace, ST7789_GraphSample sample,
                      bool usable, uint32_t now)
{
    uint32_t elapsed = now - trace->last_tick;
    if (elapsed == 0) return;
    trace->last_tick = now;

    if (usable) {
        trace->held_sample = sample;
        if (!trace->has_sample) {
            trace->has_sample = true;
            trace->phase = trace->history_ms;
        }
    }
    if (!trace->has_sample) return;

    /* Fractional sample period; repeat the last usable pair during a fault.
     * No array shifting, catch-up loop or reset when data becomes usable again.
     */
    trace->phase += elapsed * (trace->capacity - 1U);
    if (trace->phase < trace->history_ms) return;
    trace->phase %= trace->history_ms;
    trace->samples[trace->write] = trace->held_sample;
    trace->write = (trace->write + 1U) % trace->capacity;
    if (trace->count < trace->capacity) trace->count++;
    trace->version++;
}

uint16_t UI_Trace_Copy(const UI_Trace *trace, ST7789_GraphSample *destination)
{
    uint16_t oldest = (trace->write + trace->capacity - trace->count) % trace->capacity;
    for (uint16_t i = 0; i < trace->count; i++)
        destination[i] = trace->samples[(oldest + i) % trace->capacity];
    return trace->count;
}
