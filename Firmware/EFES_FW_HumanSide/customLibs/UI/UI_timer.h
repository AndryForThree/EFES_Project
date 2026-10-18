#ifndef UI_TIMER_H
#define UI_TIMER_H

#include <stdbool.h>
#include <stdint.h>

/* Private UI timer API. Main context only; TIM6 is reserved for this module. */
void UI_Timer_Init(uint16_t period_ms);
void UI_Timer_Enable(void);
void UI_Timer_Disable(void);
void UI_Timer_Reset(void);
bool UI_Timer_SetPeriod(uint16_t period_ms);
bool UI_Timer_TakeElapsed(void);

#endif
