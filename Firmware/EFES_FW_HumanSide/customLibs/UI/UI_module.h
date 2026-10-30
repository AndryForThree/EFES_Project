#ifndef UI_MODULE_H
#define UI_MODULE_H

#include <stdbool.h>
#include <stdint.h>

void UI_Init				(void);
void UI_Process				(void);
bool UI_NeedsProcess		(void);
void UI_RequestRefreshISR	(void);
void UI_SetRefreshPeriod	(uint16_t period_ms);

#endif
