#include "button.h"
#include "tim.h"
#include "main.h"
#include <stddef.h>

// COnfiguration structure for each Button
typedef struct {
	GPIO_TypeDef*	port;			// GPIO Port of the Button
	uint16_t		pin;			// GPIO Pin number of the Button
} button_config_t;

// Runtime status of each Button
typedef struct {
	bool stable_state;			// Current stable (after debouncing) state of the button
	bool debounce_state;		// Candidate state; must remain unchanged during debounce
	bool initialized;			// Flag that defines if the button is initialized and ready to be used
	bool isDebouncing;			// Flag that defines if the button is Debouncing (a change in stable state is detected, and now it is waiting for the debounce timer to confirm that change)
	bool long_press_defined;	// Flag that defines if the button is waiting to define the long press
	uint8_t debounce_cnt;		// TIM7 Tick counter to count Debouncing Time
	uint8_t long_press_cnt;		// TIM7 Tick counter to count Long Press Time
} button_state_t;

// FIFO queue of button events
typedef struct {
	button_event_t events[BUTTON_EVENT_QUEUE_SIZE];
	unsigned count;
	unsigned read_index;
	unsigned write_index;
	bool overflow;
} button_event_queue_t;

// CubeMX owns GPIO configuration. Every button needs its own EXTI line.
static const button_config_t button_config[BUTTON_ID_COUNT] = {
	[BUTTON_OK] = {OK_Button_GPIO_Port, OK_Button_Pin},
	[BUTTON_UP] = {UP_Button_GPIO_Port, UP_Button_Pin},
	[BUTTON_DOWN] = {DOWN_Button_GPIO_Port, DOWN_Button_Pin},
	[BUTTON_MODE] = {MODE_Button_GPIO_Port, MODE_Button_Pin}
};

// Internal Variables that store the current state of each button
static volatile button_state_t buttons[BUTTON_ID_COUNT];

static volatile button_event_queue_t event_queue;

//
static uint8_t debounce_ticks_threshold;
static uint8_t long_press_ticks_threshold;

// ============================================================================================================
// Private helpers
// ============================================================================================================

static bool button_isValidID (button_id_e buttonID) {
	return (unsigned)buttonID < BUTTON_ID_COUNT;
}

// Check if the button is in pressed position by reading just the GPIO (so no debounce is
// applied by this read operation)
static bool button_isPressed_noDebounce (button_id_e buttonID) {
	if (HAL_GPIO_ReadPin(button_config[buttonID].port, button_config[buttonID].pin) == BUTTON_PRESSED_LEVEL){
		// The button is in PRESSED position
		return true;
	} else {
		// The bu tton is in RELASED position
		return false;
	}
}

static void button_setEvent (button_id_e buttonID, button_event_type_e button_event_type) {
	// Check if the button event queue has space for this new event
	if (event_queue.count == BUTTON_EVENT_QUEUE_SIZE) {
		event_queue.overflow = true;
		return;
	}

	// Add the event to the queue
	button_event_t new_event = {buttonID, button_event_type};			// Create the new event
	event_queue.events[event_queue.write_index] = new_event;							// Add the event to the queue 
	event_queue.write_index = (event_queue.write_index + 1) % BUTTON_EVENT_QUEUE_SIZE;	// Update write index for the circular buffer
	event_queue.count++;																// Increment the number of events in the queue
}

static void button_startDebounce (button_id_e buttonID) {
	// Disable Button interrupts (No more interrupts calls before the de-bouncing done)
	EXTI->IMR1 &= ~button_config[buttonID].pin;

	// Set the button state to indicate the debounce process is active!
	buttons[buttonID].isDebouncing = true;
	buttons[buttonID].debounce_state = button_isPressed_noDebounce(buttonID);
	buttons[buttonID].debounce_cnt = 0;

	// Start the TIM7 Timer (if it wasn't already activated), allowing the debouncing ticks to be generated
	if (HAL_TIM_Base_GetState(&htim7) != HAL_TIM_STATE_BUSY) {
		TIM7->CNT = 0;			// Reset the timer counter
		TIM7->SR = ~TIM_SR_UIF;	// Reset the UIF Bit (it is set when the timer count up to its "target value")
		if (HAL_TIM_Base_Start_IT(&htim7) != HAL_OK) {
			Error_Handler();
		}
	}
}

static void button_rearm (button_id_e buttonID) {
	// Delete pending Interrupt requests, possibly generated during the interrupt
	// Writing 1 in this register clears the bit!
	EXTI->PR1 = button_config[buttonID].pin;

	// Enable Inpterrupt requests from the EXTI pin
	EXTI->IMR1 |= button_config[buttonID].pin;
	
	// Set the button state as ready for debouncing again
	buttons[buttonID].isDebouncing = false;
	
	// Check if a change occurred while the EXTI line was masked, and if so start a new debouncing
	// process
	if (button_isPressed_noDebounce(buttonID) != buttons[buttonID].stable_state) {
		button_startDebounce(buttonID);
	}
}

// ============================================================================================================
// Public API
// ============================================================================================================

void BUTTON_init (void) {
	// Check that values defined at compile time are acceptable
	if (	(BUTTON_TIMER_PERIOD_MS == 0)							||	// TIM7 Timer must have a period > 0
			(DEBOUNCING_PERIOD_MS < BUTTON_TIMER_PERIOD_MS)			||	// Debouncing Period must be at least 1 TIM7 period (in other case I do not have debounce at all)
			(LONG_PRESS_PERIOD_MS <= DEBOUNCING_PERIOD_MS)	||	// Long Press period must be longer that debounce (bacause I can not have long press before the PRESS state is stable!)
			(BUTTON_EVENT_QUEUE_SIZE < 1)) {					// At least 1 button event can be communicated to library users
		Error_Handler();
		return;
	}

	// Define the TIM7 tick thresolds (for debounce and long press), and make sure they can be
	// rapresented in the number of bits I used
	// The formula below implements the ceil() function with integer numbers 
	uint32_t debounce_ticks		= (DEBOUNCING_PERIOD_MS + BUTTON_TIMER_PERIOD_MS - 1U) / BUTTON_TIMER_PERIOD_MS;
	uint32_t long_press_ticks	= (LONG_PRESS_PERIOD_MS - DEBOUNCING_PERIOD_MS + BUTTON_TIMER_PERIOD_MS - 1U) / BUTTON_TIMER_PERIOD_MS;
	if (	(debounce_ticks >= UINT8_MAX) || 
			(long_press_ticks > UINT8_MAX)) {
		Error_Handler();
		return;
	}
	debounce_ticks_threshold	= (uint8_t)debounce_ticks;
	long_press_ticks_threshold	= (uint8_t)long_press_ticks;

	// Disable all interrupts handled by this library
	HAL_NVIC_DisableIRQ(EXTI15_10_IRQn);
	HAL_NVIC_DisableIRQ(TIM7_IRQn);
	
	// Stop the timer and disabilitate the interrupt requests
	if (HAL_TIM_Base_Stop_IT(&htim7) != HAL_OK) {
		Error_Handler();
	}
	TIM7->CNT = 0;			// Reset the timer counter
	TIM7->SR = ~TIM_SR_UIF;	// Reset the UIF Bit (it is set when the timer count up to its "target value")

	HAL_NVIC_ClearPendingIRQ(TIM7_IRQn);
	HAL_NVIC_ClearPendingIRQ(EXTI15_10_IRQn);
	event_queue = (button_event_queue_t){0};

	for (button_id_e buttonID = BUTTON_OK; buttonID < BUTTON_ID_COUNT; buttonID++) {
		// Initialize the button state structure with all 0's
		buttons[buttonID] = (button_state_t){0};

		// Ignore a button held at startup until it has been released.
		bool isCurrentlyPressed = button_isPressed_noDebounce(buttonID);
		buttons[buttonID].stable_state = isCurrentlyPressed;
		buttons[buttonID].long_press_defined = true;
		buttons[buttonID].initialized = true;

		// Delete pending Interrupt requests and enable the EXTI pin after initialization
		button_rearm(buttonID);
	}

	// Enable interrupt delivery only after all buttons are ready
	HAL_NVIC_EnableIRQ(TIM7_IRQn);
	HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
}


bool button_getState_stable (button_id_e buttonID) {
	// Check that the accessed button is initilized
	if ((!button_isValidID(buttonID))	||
		(!buttons[buttonID].initialized)) {
		Error_Handler();
	}
	return buttons[buttonID].stable_state;
}


bool button_hasEvents (void) {
	return (event_queue.count != 0);
}


bool button_getEvent (button_event_t *event) {
	if (event == NULL) {
		Error_Handler();
	}

	// Check if there is an event to be returned
	if (event_queue.count == 0) {
		return false;
	}
	
	// Execute the extraction of the event in a Critical Section
	// If an interrupt comes while I'm executing the extraction, a mixed 
	// state can be read, generating possibile errors
	uint32_t mask = lock();
	
	*event = event_queue.events[event_queue.read_index];
	event_queue.read_index = (event_queue.read_index + 1U) % BUTTON_EVENT_QUEUE_SIZE;
	event_queue.count--;

	// Unlock the critical section
	unlock(mask);

	return true;
}

bool button_hasOverflow (void) {
	return event_queue.overflow;
}

void button_clearOverflow (void) {
	event_queue.overflow = false;
}

void button_clearEvents (void) {
	uint32_t mask = lock();
	event_queue.read_index = 0;
	event_queue.write_index = 0;
	event_queue.count = 0;
	event_queue.overflow = false;
	unlock(mask);
}

// ============================================================================================================
// Interrupt handling (EXTI and TIM7 use the same preemption priority)
// ============================================================================================================

// Callback function for the EXTI interrupt!
void HAL_GPIO_EXTI_Callback (uint16_t GPIO_Pin) {
	// Loop through all the buttons available in the libary, to find the one that generated the interrupt
	for (unsigned buttonID = 0; buttonID < BUTTON_ID_COUNT; buttonID++) {
		if ((button_config[buttonID].pin == GPIO_Pin)	&&		// Check if the button pin that generated the interrupt is the currently indexed one
			(buttons[buttonID].initialized)				&&		// Check if the currently indexed button is initialized
			(!buttons[buttonID].isDebouncing)) {				// Check if the currently indexed button is already debouncing (so no interrupt should be generated)
			button_startDebounce((button_id_e)buttonID);
		}
	}
}

// This function is called at each TIM7 interrupt
void button_timerElapsedISR (void) {
	// Flag that indicates if the TIM7 is still needed by the Button Library
	bool control_pending = false;

	// Analyze each button available
	for (button_id_e buttonID = BUTTON_OK; buttonID < BUTTON_ID_COUNT; buttonID++) {
		// Check if the current button is iniaialized
		if (!buttons[buttonID].initialized) continue;

		// Increment the Long Press counter
		if ((buttons[buttonID].stable_state)					&&					// Button must be in Pressed Stable state
			(!buttons[buttonID].long_press_defined)				&& 					// The Button Long Press is not yet evaluated
			(buttons[buttonID].long_press_cnt < long_press_ticks_threshold)) {		// The Long Press counter did not reach the threshold yet
			buttons[buttonID].long_press_cnt++;
		}
		
		// Handle the current button debouncing
		if (buttons[buttonID].isDebouncing) {
			// Restart the debounce interval whenever the sampled level changes.
			bool isCurrentlyPressed = button_isPressed_noDebounce(buttonID);
			if (isCurrentlyPressed != buttons[buttonID].debounce_state) {
				buttons[buttonID].debounce_state = isCurrentlyPressed;
				buttons[buttonID].debounce_cnt = 0;
			} else {
				buttons[buttonID].debounce_cnt++;
			}

			// Check if I reached the debouncing threshold
			if (buttons[buttonID].debounce_cnt >= debounce_ticks_threshold) {
				
				// Commit only after consecutive samples confirmed the same state.
				if (isCurrentlyPressed != buttons[buttonID].stable_state) {
					// Commit the Button state after debouncing
					buttons[buttonID].stable_state = isCurrentlyPressed;

					// Start the Long Press counter only if the new stable state is PRESSED (RELASED
					// state does not check for a long relased state!!)
					if (isCurrentlyPressed) {
						buttons[buttonID].long_press_defined = false;
						buttons[buttonID].long_press_cnt = 0;

					// If the new state is RELASED, generate a SHORT_PRESS event ONLY if the 
					// long press event was not already defined (basically the button was relased
					// before the long press condition was verified)	
					} else if (!buttons[buttonID].long_press_defined) {
						button_setEvent(buttonID, BUTTON_SHORT_PRESS);
					}
				}

				// Re-activate the Interrupt for the Button after the debouncing ended!
				button_rearm(buttonID);
			}
		}

		// Wait for release debounce before deciding whether a press is long.
		bool waiting_long = (	(buttons[buttonID].stable_state)	&& 		// Long Press is evaluated only if the Stable state is PRESSED
								(!buttons[buttonID].long_press_defined));					// Long Press is evalueted just one time && !buttons[buttonID].isDebouncing &&
		

		if (	(waiting_long)	&&
				(!buttons[buttonID].isDebouncing)	&&
				(buttons[buttonID].long_press_cnt >= long_press_ticks_threshold)) {	// Check if the Long Press evaluation time has elapsed
			button_setEvent(buttonID, BUTTON_LONG_PRESS);
			buttons[buttonID].long_press_defined = true;
			waiting_long = false;
		}
		
		// Check if the TIM7 is still needed
		if (buttons[buttonID].isDebouncing || waiting_long) {
			control_pending = true;
		};
	}

	// Disable the TIM7 Timer ONLY IF no button needs it (basically no button is in debouncing or
	// in long press evaluation states!)
	if (!control_pending) {
		if (HAL_TIM_Base_Stop_IT(&htim7) != HAL_OK) {
			Error_Handler();
		}
	}
}
