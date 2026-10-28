#ifndef __BUTTON_H
#define __BUTTON_H

#include <stdbool.h>
#include <stdint.h>

// Define the IDs for the avaiable buttons!
typedef enum {
	BUTTON_OK,
	BUTTON_UP,
	BUTTON_DOWN,
	BUTTON_MODE,
	BUTTON_ID_COUNT
} button_id_e;

// User configurable constants
#define BUTTON_TIMER_PERIOD_MS		5	// Must match the TIM7 period configured in CubeMX
#define BUTTON_PRESSED_LEVEL		GPIO_PIN_SET
#define DEBOUNCING_PERIOD_MS		30
#define LONG_PRESS_PERIOD_MS		1000
#define BUTTON_EVENT_QUEUE_SIZE		16

typedef enum {
	BUTTON_SHORT_PRESS,
	BUTTON_LONG_PRESS
} button_event_type_e;

typedef struct {
	button_id_e			buttonID;
	button_event_type_e	type;
} button_event_t;

// Public Methods (main context only; initialize after GPIO and TIM7)
void BUTTON_init				(void);
bool button_getState_stable		(button_id_e buttonID);
bool button_hasEvents			(void);
bool button_getEvent			(button_event_t *event);
bool button_hasOverflow			(void);
void button_clearOverflow		(void);
void button_clearEvents			(void);

/* Called only for TIM7 from the shared HAL timer callback. */
void button_timerElapsedISR		(void);

#endif
