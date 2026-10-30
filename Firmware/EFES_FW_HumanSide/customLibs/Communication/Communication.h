#ifndef COMMUNICATION_H
#define COMMUNICATION_H

#include <stdbool.h>
#include <stdint.h>

// Safety timeouts for "stale" safety critical data
#define SENSOR_TIMEOUT_MS	100	// Maximum time before the Steering Wheel Sensor data become "stale"
#define ROAD_TIMEOUT_MS		100	// Maximum time before the Road Side Data become "stale"

typedef struct {
	uint32_t	received_at_ms; 			// SPI Steering Wheel Sensor Reception time (SysTick)
	int16_t		channel_a_angle_deci_deg;	// Steering Wheel Sensor Channel A reading (deci degree)
	int16_t		channel_b_angle_deci_deg;	// Steering Wheel Sensor Channel B reading (deci degree)
	uint16_t	deviation_limit_deci_deg; 	// 
	bool		channel_a_valid;			// Steering Wheel Sensor Channel A "valid flag"
	bool		channel_b_valid;			// Steering Wheel Sensor Channel B "valid flag"
	bool		plausibility_fault; 		// Steering Wheel Sensor Plausibility check
	bool		valid;						// Received sample is valid and usable
	bool		stale;						// No fresh sample received
} Sensor_State;

typedef struct {
	uint32_t	received_at_ms; 			// CAN Read Side Update Reception time (SysTick)
	int16_t		actual_angle_deci_deg;		// 
	bool		valid;
	bool		stale;
} RoadFeedback_State;

typedef struct {
	int16_t			steering_angle_deci_deg; /* Tenths of a degree; positive = right. */
	
	// Both in the same road-wheel reference; the App provides the target and
	// the actual feedback from the road-side ECU. No steering ratio in the UI
	int16_t			road_requested_angle_deci_deg;
	uint16_t		vehicle_speed_kmh;     /* Integer km/h, 0..999. */
	uint16_t		steering_ratio_deci;   /* Ratio in tenths: 128 means 12.8:1. */
	bool			can_online;
	bool			actuator_ready;
	bool			speed_simulated;
} Operating_State;

/* Latest-state notifications, owned by the producers, not by App.
 * Publish on reception or a status change (including a stale timeout).
 * Repeated publications before TakeUpdate replace the previous state.
 * Pointers must be non-NULL. Publication is also allowed from an ISR;
 * Init and TakeUpdate are called from main. Init precedes App_Init.
 */
void Communication_Init(void);

void Sensor_PublishState(const Sensor_State *state);
bool Sensor_TakeUpdate(Sensor_State *state);
bool Sensor_HasUpdate(void);

void Road_PublishState(const RoadFeedback_State *state);
bool Road_TakeUpdate(RoadFeedback_State *state);
bool Road_HasUpdate(void);

void Operating_PublishState(const Operating_State *state);
bool Operating_TakeUpdate(Operating_State *state);
bool Operating_HasUpdate(void);

#endif
