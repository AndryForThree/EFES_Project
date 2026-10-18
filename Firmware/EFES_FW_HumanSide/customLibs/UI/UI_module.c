#include "UI_module.h"
#include "UI_timer.h"
#include "UI_home.h"
#include "UI_sensor.h"
#include "UI_header.h"
#include "UI_history.h"
#include "UI_steering.h"
#include "UI_mode.h"
#include "st7789.h"

#define UI_EVENT_QUEUE_SIZE 8U
#define UI_REFRESH_PERIOD_MS 20U

/* Only pages before PAGE_COUNT participate in normal navigation. */
typedef enum {
    PAGE_HOME,
    PAGE_SENSOR,
    PAGE_STEERING,
    PAGE_COUNT,
    PAGE_ALARM
} UI_Page;

static const char *const page_titles[PAGE_COUNT] = {
    "HOME", "SENSOR DIAGNOSTICS", "STEERING RESPONSE"
};

typedef enum {
    RENDER_IDLE,
    RENDER_CLEAR,
    RENDER_HEADER,
    RENDER_PAGE
} UI_RenderPhase;

typedef struct {
    UI_State state;
    UI_State render_state;
    UI_Page selected_page;
    UI_Page active_page;
    UI_RenderPhase phase;
    UI_Event events[UI_EVENT_QUEUE_SIZE];
    uint8_t read_index;
    uint8_t write_index;
    uint8_t event_count;
    bool refresh_pending;
} UI_Context;

static UI_Context ui;

uint16_t UI_SensorDeviation(const UI_State *state)
{
    int32_t difference = (int32_t)state->channel_a_angle_deci_deg - state->channel_b_angle_deci_deg;
    return (uint16_t)(difference < 0 ? -difference : difference);
}

bool UI_SensorStale(const UI_State *state, uint32_t now)
{
    return (uint32_t)(now - state->sensor_sample_received_at_ms) > UI_SENSOR_STALE_MS;
}

/* Page functions will draw from ui.render_state, which stays unchanged
 * until the whole refresh completes. Each call performs one small step
 * and returns true only when the page refresh is finished.
 */
static bool AlarmPage_Process(void)
{
    /* Alarm presentation will be defined with the page layout. */
    return true;
}

void UI_Init(void)
{
    ui = (UI_Context){0};
    ui.selected_page = PAGE_HOME;
    ui.active_page = PAGE_HOME;
    ui.phase = RENDER_CLEAR;

    UI_History_Init();
    UI_Steering_Init();
    UI_Timer_Init(UI_REFRESH_PERIOD_MS);
    UI_Timer_Enable();
}

void UI_SetState(const UI_State *state)
{
    ui.state = *state;
}

bool UI_PostEvent(UI_Event event)
{
    if (event != UI_EVENT_NEXT_PAGE && event != UI_EVENT_PREVIOUS_PAGE)
        return false;
    if (ui.state.alarms != 0 || ui.event_count == UI_EVENT_QUEUE_SIZE)
        return false;

    ui.events[ui.write_index] = event;
    ui.write_index = (ui.write_index + 1U) % UI_EVENT_QUEUE_SIZE;
    ui.event_count++;
    return true;
}

bool UI_SetRefreshPeriod(uint16_t period_ms)
{
    return UI_Timer_SetPeriod(period_ms);
}

void UI_Process(void)
{
    UI_Page requested_page;

    /* History runs even when Home is selected or the driver is transferring. */
    uint32_t now = HAL_GetTick();
    UI_History_Process(&ui.state, now);
    UI_Steering_Sample(&ui.state, now);
    if (UI_Timer_TakeElapsed()) ui.refresh_pending = true;

    if (ui.state.alarms != 0) {
        /* Do not replay navigation after an alarm disappears. */
        ui.read_index = 0;
        ui.write_index = 0;
        ui.event_count = 0;
    } else if (ui.event_count != 0) {
        UI_Event event = ui.events[ui.read_index];
        ui.read_index = (ui.read_index + 1U) % UI_EVENT_QUEUE_SIZE;
        ui.event_count--;

        if (event == UI_EVENT_NEXT_PAGE)
            ui.selected_page = (ui.selected_page + 1) % PAGE_COUNT;
        else
            ui.selected_page = (ui.selected_page + PAGE_COUNT - 1) % PAGE_COUNT;
    }

    requested_page = ui.state.alarms != 0 ? PAGE_ALARM : ui.selected_page;

    /* Never wait for the driver or change buffers used by an active draw.
     * A driver error also stops rendering here, without automatic retries.
     */
    if (ST7789_GetState() != ST7789_STATE_IDLE) return;

    if (requested_page != ui.active_page) {
        ui.active_page = requested_page;
        ui.refresh_pending = false;
        ui.phase = RENDER_CLEAR;
    }

    switch (ui.phase) {
    case RENDER_IDLE:
        if (!ui.refresh_pending) return;
        ui.render_state = ui.state;
        ui.refresh_pending = false;
        ui.phase = RENDER_PAGE;
        break;

    case RENDER_CLEAR:
        ui.render_state = ui.state;
        if (ST7789_Fill_Color(UI_BACKGROUND) == ST7789_OK) {
            UI_Home_Reset();
            UI_Sensor_Reset();
            UI_Steering_Reset();
            UI_Mode_Reset();
            if (ui.active_page != PAGE_HOME && ui.active_page != PAGE_ALARM) {
                UI_Header_Reset(page_titles[ui.active_page], ui.active_page + 1, PAGE_COUNT);
                ui.phase = RENDER_HEADER;
            } else {
                ui.phase = RENDER_PAGE;
            }
        }
        break;

    case RENDER_HEADER:
        if (UI_Header_Process()) ui.phase = RENDER_PAGE;
        break;

    case RENDER_PAGE:
        if (ui.active_page == PAGE_ALARM) {
            if (AlarmPage_Process()) ui.phase = RENDER_IDLE;
        } else if (ui.active_page == PAGE_SENSOR) {
            if (UI_Sensor_Process(&ui.render_state)) ui.phase = RENDER_IDLE;
        } else if (ui.active_page == PAGE_STEERING) {
            if (UI_Steering_Process(&ui.render_state)) ui.phase = RENDER_IDLE;
        } else {
            if (UI_Home_Process(&ui.render_state)) ui.phase = RENDER_IDLE;
        }
        break;
    }
}
