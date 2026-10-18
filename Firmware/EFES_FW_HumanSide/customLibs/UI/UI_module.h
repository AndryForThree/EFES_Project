#ifndef UI_MODULE_H
#define UI_MODULE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    UI_DRIVE_NORMAL,
    UI_DRIVE_ECO,
    UI_DRIVE_SPORT
} UI_DriveMode;

typedef struct {
    /* Zero means no alarm. Individual alarm bits will be defined with the App. */
    uint32_t alarms;
    UI_DriveMode drive_mode;
    int16_t steering_angle_deci_deg; /* Tenths of a degree; positive = right. */
    /* Both in the same road-wheel reference; the App provides the target and
     * the actual feedback from the road-side ECU. No steering ratio in the UI.
     */
    int16_t road_requested_angle_deci_deg;
    int16_t road_actual_angle_deci_deg;
    uint32_t road_feedback_received_at_ms;
    bool road_feedback_valid;
    uint16_t vehicle_speed_kmh;     /* Integer km/h, 0..999. */
    uint32_t sensor_sample_received_at_ms; /* HAL_GetTick at reception, not UI_SetState time. */
    int16_t channel_a_angle_deci_deg;
    int16_t channel_b_angle_deci_deg;
    uint16_t sensor_deviation_limit_deci_deg; /* Configured FPGA limit, must be > 0. */
    bool channel_a_valid;
    bool channel_b_valid;
    bool sensor_plausibility_fault; /* Sensor SPI/GPIO verdict, never inferred by UI. */
    uint16_t steering_ratio_deci;   /* Ratio in tenths: 128 means 12.8:1. */
    bool sensors_valid;
    bool can_online;
    bool actuator_ready;
    bool speed_simulated;
} UI_State;

typedef enum {
    UI_EVENT_NEXT_PAGE,
    UI_EVENT_PREVIOUS_PAGE
} UI_Event;

/* Call all public functions from the main context, never from an ISR.
 * Init follows ST7789_Init; Process runs on every superloop iteration,
 * alongside ST7789_Process. The UI is the only display drawing client.
 */
void UI_Init(void);
void UI_Process(void);
void UI_SetState(const UI_State *state);

/* Copies one event into an 8-entry FIFO. Returns false if full, invalid,
 * or navigation is blocked by an active alarm. Never waits for space.
 */
bool UI_PostEvent(UI_Event event);

/* Range: 1..6553 ms. Restarts the refresh interval; default is 20 ms.
 * This controls new refreshes, not the progress of an active drawing.
 */
bool UI_SetRefreshPeriod(uint16_t period_ms);

#endif
