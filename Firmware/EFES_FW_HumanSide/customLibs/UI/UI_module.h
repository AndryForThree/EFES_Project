#ifndef UI_MODULE_H
#define UI_MODULE_H

#include <stdbool.h>
#include <stdint.h>



/* Call Init, Process and SetRefreshPeriod from main, never from an ISR.
 * Init follows ST7789_Init; Process runs on every superloop iteration,
 * alongside ST7789_Process. The UI is the only display drawing client.
 */
void UI_Init(void);
void UI_Process(void);
/* True when rendering can advance without waiting for the display driver.
 * Check together with ST7789_NeedsProcess before entering Sleep.
 */
bool UI_NeedsProcess(void);

/* TIM6 interrupt hook: requests a refresh without drawing or changing snapshots.
 * Multiple requests are coalesced until the main loop starts a new refresh.
 */
void UI_RequestRefreshISR(void);

/* Range: 1..6553 ms. Restarts the refresh interval; default is 20 ms.
 * This controls new refreshes, not the progress of an active drawing.
 * Requires TIM6 initialized by CubeMX at 10 kHz, with ARR preload disabled.
 * Preserves whether the timer is running. Returns false for an invalid period
 * or a HAL failure. Call from main, never from an ISR.
 */
bool UI_SetRefreshPeriod(uint16_t period_ms);

#endif
