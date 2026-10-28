#include "Communication.h"
#include "main.h"

static Sensor_State sensor_state;
static volatile bool sensor_pending;

static RoadFeedback_State road_state;
static volatile bool road_pending;

static Operating_State operating_state;
static volatile bool operating_pending;

void Communication_Init(void)
{
	sensor_state = (Sensor_State){.stale = true};
	road_state = (RoadFeedback_State){.stale = true};
	operating_state = (Operating_State){0};
	sensor_pending = false;
	road_pending = false;
	operating_pending = false;
}

void Sensor_PublishState(const Sensor_State *state)
{
	uint32_t mask = lock();
	sensor_state = *state;
	sensor_pending = true;
	unlock(mask);
}

bool Sensor_TakeUpdate(Sensor_State *state)
{
	uint32_t mask = lock();
	bool pending = sensor_pending;
	if (pending) {
		*state = sensor_state;
		sensor_pending = false;
	}
	unlock(mask);
	return pending;
}

bool Sensor_HasUpdate(void)
{
	return sensor_pending;
}

void Road_PublishState(const RoadFeedback_State *state)
{
	uint32_t mask = lock();
	road_state = *state;
	road_pending = true;
	unlock(mask);
}

bool Road_TakeUpdate(RoadFeedback_State *state)
{
	uint32_t mask = lock();
	bool pending = road_pending;
	if (pending) {
		*state = road_state;
		road_pending = false;
	}
	unlock(mask);
	return pending;
}

bool Road_HasUpdate(void)
{
	return road_pending;
}

void Operating_PublishState(const Operating_State *state)
{
	uint32_t mask = lock();
	operating_state = *state;
	operating_pending = true;
	unlock(mask);
}

bool Operating_TakeUpdate(Operating_State *state)
{
	uint32_t mask = lock();
	bool pending = operating_pending;
	if (pending) {
		*state = operating_state;
		operating_pending = false;
	}
	unlock(mask);
	return pending;
}

bool Operating_HasUpdate(void)
{
	return operating_pending;
}

