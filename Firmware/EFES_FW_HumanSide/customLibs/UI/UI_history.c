#include "UI_history.h"
#include "UI_trace.h"

static ST7789_GraphSample samples[GRAPH_SAMPLES];
static UI_Trace history;

void UI_History_Init(void)
{
    UI_Trace_Init(&history, samples, GRAPH_SAMPLES, GRAPH_HISTORY_MS);
}

void UI_History_Process(const UI_State *state, uint32_t now)
{
    bool usable = state->channel_a_valid && state->channel_b_valid &&
                  !state->sensor_plausibility_fault && !UI_SensorStale(state, now);
    UI_Trace_Process(&history, (ST7789_GraphSample){
        state->channel_a_angle_deci_deg, state->channel_b_angle_deci_deg
    }, usable, now);
}

uint32_t UI_History_Version(void)
{
    return history.version;
}

uint16_t UI_History_Copy(ST7789_GraphSample *destination)
{
    return UI_Trace_Copy(&history, destination);
}
