#include "DRV8874.h"

#include "main.h"
#include "tim.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>

// Application misuse is fatal; the project's Error_Handler must never return.
_Noreturn void Error_Handler(void);

// ==============================================================================================
// Road Side hardware - configure CubeMX and the mapping defines in DRV8874.h
// ==============================================================================================

// INPUT1 -> EN/IN1; INPUT2 -> PH/IN2 (LOW/HIGH PWM endpoints in PH/EN).
// VREF -> optional PWM-to-VREF circuit; vrefMax_mV=0 selects fixed VREF.
// GPIO labels: DRV8874_SLEEP (output, initial LOW), DRV8874_FAULT (EXTI input, both edges).
// PMODE and IMODE are wired/configured outside this driver and must match config.
// PWM must be active-HIGH PWM1, edge-aligned, counting UP.
// Reserve one compare count above ARR for a true 100% duty (ARR < counter maximum).
// ADC: update DRV8874_ipropiAdcSample from the completed IPROPI conversion/DMA buffer.
// This declaration uses the timer handle selected in DRV8874.h.
extern TIM_HandleTypeDef DRV8874_PWM_TIMER;

volatile uint32_t DRV8874_ipropiAdcSample = UINT32_MAX;
static volatile bool DRV8874_faultActive = false;

// ==============================================================================================
// Private helpers
// ==============================================================================================

// Private helpers prototypes
static void DRV8874_checkOpen(DRV8874_Object *dev);
static void DRV8874_validateConfig(const DRV8874_Config *config);
static DRV8874_Status DRV8874_failSafe(DRV8874_Object *dev);
static DRV8874_Status DRV8874_applyDuty(DRV8874_Object *dev, int16_t dutyPermille);



static void DRV8874_checkOpen(DRV8874_Object *dev) {
	if(dev == NULL) {
		Error_Handler();
	}
	if(!dev->isOpen) {
		Error_Handler();
	}
}

static void DRV8874_validateConfig(const DRV8874_Config *config) {
	if(config == NULL) {
		Error_Handler();
	}
	if(((config->controlMode != DRV8874_CONTROL_PH_EN) &&
		(config->controlMode != DRV8874_CONTROL_IN_IN)) ||
		((uint32_t)config->currentMode > DRV8874_IMODE_FIXED_LATCH) ||
		((uint32_t)config->pwmOffMode > DRV8874_PWM_OFF_BRAKE)) {
		Error_Handler();
	}
	if((config->pwmFrequencyHz == 0U) || (config->pwmFrequencyHz > DRV8874_PWM_MAX_HZ)) {
		Error_Handler();
	}
	if((config->vref_mV > DRV8874_VREF_MAX_MV) || (config->vrefMax_mV > DRV8874_VREF_MAX_MV)) {
		Error_Handler();
	}
	if((config->vrefMax_mV != 0U) && (config->vref_mV > config->vrefMax_mV)) {
		Error_Handler();
	}
	if((config->ipropiResistorOhm != 0U) &&
		((config->adcReference_mV == 0U) || (config->adcFullScale == 0U))) {
		Error_Handler();
	}
}

// Any failure while changing motor inputs forces nSLEEP LOW.
// HAL_GPIO_WritePin has no return status; it cannot detect physical pin failures.
static DRV8874_Status DRV8874_failSafe(DRV8874_Object *dev) {
	HAL_GPIO_WritePin(DRV8874_SLEEP_PORT, DRV8874_SLEEP_PIN, GPIO_PIN_RESET);
	dev->isAwake = false;
	dev->state = DRV8874_STATE_SLEEP;
	dev->commandedDutyPermille = 0;
	HAL_Delay(DRV8874_SLEEP_DELAY_MS);
	return DRV8874_STATUS_IO_ERROR;
}

// ==============================================================================================
// General driver lifecycle
// ==============================================================================================

DRV8874_Status DRV8874_init(DRV8874_Object *dev, const DRV8874_Config *config) {
	if(dev == NULL) {
		Error_Handler();
	}
	DRV8874_validateConfig(config);

	// Initialize the software state first. The caller must not re-init an already-open instance;
	// close it before reusing the same object.
	memset(dev, 0, sizeof(*dev));
	dev->config = *config;
	dev->state = DRV8874_STATE_UNKNOWN;

	// Disable the power stage before configuring inputs or the optional VREF source.
	HAL_GPIO_WritePin(DRV8874_SLEEP_PORT, DRV8874_SLEEP_PIN, GPIO_PIN_RESET);
	if(DRV8874_PWM_TIMER.Instance == NULL) {
		Error_Handler();
	}
	const uint32_t inputMaximum = IS_TIM_32B_COUNTER_INSTANCE(DRV8874_PWM_TIMER.Instance) ? UINT32_MAX : UINT16_MAX;
	if((DRV8874_PWM_TIMER.Init.CounterMode != TIM_COUNTERMODE_UP) ||
		(__HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) == 0U) ||
		(__HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) >= inputMaximum)) {
		Error_Handler();
	}
	// Immediate writes preserve the non-driving interval before changing direction.
	__HAL_TIM_DISABLE_OCxPRELOAD(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL);
	__HAL_TIM_DISABLE_OCxPRELOAD(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
	if(dev->config.vrefMax_mV != 0U) {
		const uint64_t period = (uint64_t)__HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1U;
		const uint32_t compare = (uint32_t)((period * dev->config.vref_mV +
			dev->config.vrefMax_mV / 2U) / dev->config.vrefMax_mV);
		// Do not silently replace a nonzero current limit with zero VREF.
		if((dev->config.vref_mV != 0U) && (compare == 0U)) {
			Error_Handler();
		}
		__HAL_TIM_DISABLE_OCxPRELOAD(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL);
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL, compare);
	}
	if((HAL_TIM_PWM_Start(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL) != HAL_OK) ||
		(HAL_TIM_PWM_Start(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL) != HAL_OK) ||
		((dev->config.vrefMax_mV != 0U) && (HAL_TIM_PWM_Start(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL) != HAL_OK))) {
		// Release any channels already started so initialization can be retried.
		HAL_TIM_PWM_Stop(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL);
		HAL_TIM_PWM_Stop(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL);
		if(dev->config.vrefMax_mV != 0U) {
			HAL_TIM_PWM_Stop(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL);
		}
		return DRV8874_failSafe(dev);
	}

	HAL_Delay(DRV8874_SLEEP_DELAY_MS);
	// Capture an already-active fault; EXTI handles subsequent changes.
	// Keep the initial sample and store together so an ISR cannot overwrite a newer level.
	const uint32_t interruptMask = __get_PRIMASK();
	__disable_irq();
	DRV8874_faultActive = HAL_GPIO_ReadPin(DRV8874_FAULT_PORT,
		DRV8874_FAULT_PIN) == GPIO_PIN_RESET;
	__set_PRIMASK(interruptMask);
	dev->state = DRV8874_STATE_SLEEP;
	dev->isOpen = true;
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_close(DRV8874_Object *dev) {
	DRV8874_Status status = DRV8874_sleep(dev);
	if(status != DRV8874_STATUS_OK) {
		return status;
	}
	if((HAL_TIM_PWM_Stop(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL) != HAL_OK) ||
		(HAL_TIM_PWM_Stop(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL) != HAL_OK)) {
		return DRV8874_failSafe(dev);
	}
	if((dev->config.vrefMax_mV != 0U) &&
		(HAL_TIM_PWM_Stop(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL) != HAL_OK)) {
		return DRV8874_failSafe(dev);
	}
	memset(dev, 0, sizeof(*dev));
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_sleep(DRV8874_Object *dev) {
	DRV8874_checkOpen(dev);
	HAL_GPIO_WritePin(DRV8874_SLEEP_PORT, DRV8874_SLEEP_PIN, GPIO_PIN_RESET);
	dev->isAwake = false;
	dev->state = DRV8874_STATE_SLEEP;
	dev->commandedDutyPermille = 0;
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
	HAL_Delay(DRV8874_SLEEP_DELAY_MS);
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_wake(DRV8874_Object *dev) {
	DRV8874_checkOpen(dev);
	if(dev->state == DRV8874_STATE_UNKNOWN) {
		return DRV8874_STATUS_IO_ERROR;
	}
	if(dev->isAwake) {
		return DRV8874_STATUS_OK;
	}
	// Reset the inputs before enabling the H-bridge.
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
	HAL_GPIO_WritePin(DRV8874_SLEEP_PORT, DRV8874_SLEEP_PIN, GPIO_PIN_SET);
	HAL_Delay(DRV8874_WAKE_DELAY_MS);
	dev->isAwake = true;
	dev->commandedDutyPermille = 0;
	// With both inputs LOW, PH/EN brakes and IN/IN coasts.
	dev->state = (dev->config.controlMode == DRV8874_CONTROL_PH_EN)
		? DRV8874_STATE_BRAKE : DRV8874_STATE_COAST;
	return DRV8874_STATUS_OK;
}

// ==============================================================================================
// H-bridge control
// ==============================================================================================

static DRV8874_Status DRV8874_applyDuty(DRV8874_Object *dev, int16_t dutyPermille) {
	const uint16_t magnitude = (uint16_t)(dutyPermille < 0 ? -dutyPermille : dutyPermille);
	const bool positive = dutyPermille >= 0;
	const uint32_t period = __HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1U;
	const uint32_t compare = (uint32_t)(((uint64_t)period * magnitude + 500U) / 1000U);

	// Changing direction while actively driving: first enter a non-driving state.
	// This is only a logic-level transition: mechanical speed/torque ramps belong to the
	// application-level controller, not the device driver.
	if((dev->state != DRV8874_STATE_DRIVE) ||
		((dev->commandedDutyPermille < 0) != (dutyPermille < 0))) {
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
		if(dev->config.controlMode == DRV8874_CONTROL_IN_IN) {
			__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
		}
	}

	if(dev->config.controlMode == DRV8874_CONTROL_PH_EN) {
		// In PH/EN, EN=0 is brake (low-side slow decay), not coast.
		// Set EN to zero before any direction change.
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, positive ? period : 0U);
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, compare);
	}
	else {
		// IN/IN: choose either drive/coast or drive/brake PWM.
		// Set both inputs to LOW before changing direction/off-time strategy.
		if(dev->config.pwmOffMode == DRV8874_PWM_OFF_COAST) {
			if(positive) {
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, compare);
			}
			else {
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, compare);
			}
		}
		else {
			// For drive/brake: hold one input HIGH, PWM the other with inverse duty.
			const uint32_t inverse = (uint32_t)(((uint64_t)period * (1000U - magnitude) + 500U) / 1000U);
			if(positive) {
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, period);
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, inverse);
			}
			else {
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, period);
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, inverse);
			}
		}
	}

	dev->commandedDutyPermille = dutyPermille;
	dev->state = (magnitude != 0U) ? DRV8874_STATE_DRIVE :
		((dev->config.controlMode == DRV8874_CONTROL_PH_EN ||
		dev->config.pwmOffMode == DRV8874_PWM_OFF_BRAKE) ? DRV8874_STATE_BRAKE : DRV8874_STATE_COAST);
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_setDutyCycle(DRV8874_Object *dev, int16_t dutyPermille) {
	DRV8874_checkOpen(dev);
	if((dutyPermille < -1000) || (dutyPermille > 1000)) {
		Error_Handler();
	}
	if(dev->state == DRV8874_STATE_UNKNOWN) {
		return DRV8874_STATUS_IO_ERROR;
	}
	if(!dev->isAwake) {
		Error_Handler();
	}
	return DRV8874_applyDuty(dev, dutyPermille);
}

DRV8874_Status DRV8874_brake(DRV8874_Object *dev) {
	DRV8874_checkOpen(dev);
	if(dev->state == DRV8874_STATE_UNKNOWN) {
		return DRV8874_STATUS_IO_ERROR;
	}
	if(!dev->isAwake) {
		Error_Handler();
	}
	if(dev->config.controlMode == DRV8874_CONTROL_PH_EN) {
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U); // EN LOW -> both lows ON
	}
	else {
		// Go via coast (both inputs LOW) before asserting both HIGH for brake.
		const uint32_t period = __HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1U;
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, period);
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, period);
	}
	dev->state = DRV8874_STATE_BRAKE;
	dev->commandedDutyPermille = 0;
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_coast(DRV8874_Object *dev) {
	DRV8874_checkOpen(dev);
	if(dev->config.controlMode != DRV8874_CONTROL_IN_IN) {
		Error_Handler();
	}
	if(dev->state == DRV8874_STATE_UNKNOWN) {
		return DRV8874_STATUS_IO_ERROR;
	}
	if(!dev->isAwake) {
		Error_Handler();
	}
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT1_CHANNEL, 0U);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_INPUT2_CHANNEL, 0U);
	dev->state = DRV8874_STATE_COAST;
	dev->commandedDutyPermille = 0;
	return DRV8874_STATUS_OK;
}

// ==============================================================================================
// Current sensing and regulation
// ==============================================================================================

DRV8874_Status DRV8874_readCurrent_mA(DRV8874_Object *dev, uint32_t *current_mA) {
	DRV8874_checkOpen(dev);
	if(current_mA == NULL) {
		Error_Handler();
	}
	if((dev->config.ipropiResistorOhm == 0U)) {
		Error_Handler();
	}
	if(dev->state == DRV8874_STATE_UNKNOWN) {
		return DRV8874_STATUS_IO_ERROR;
	}
	if(!dev->isAwake) {
		Error_Handler();
	}
	if(dev->state == DRV8874_STATE_COAST) {
		return DRV8874_STATUS_NO_MEASUREMENT;
	}

	// Read a single completed sample; acquisition runs outside the driver, without polling.
	const uint32_t sample = DRV8874_ipropiAdcSample;
	if(sample == UINT32_MAX) {
		return DRV8874_STATUS_NO_MEASUREMENT;
	}
	if(sample > dev->config.adcFullScale) {
		return DRV8874_STATUS_IO_ERROR;
	}
	const uint32_t voltage_mV = (uint32_t)(((uint64_t)sample * dev->config.adcReference_mV +
		dev->config.adcFullScale / 2U) / dev->config.adcFullScale);
	// I(A) = V(V) / (R(ohm) * AIPROPI(A/A)). Return nonnegative current in mA.
	// This is an estimate, affected by mirror accuracy and possible VREF clamping.
	const uint64_t ratio = (uint64_t)dev->config.ipropiResistorOhm * DRV8874_AIPROPI_TYP_UA_PER_A;
	const uint64_t current = ((uint64_t)voltage_mV * 1000000U + ratio / 2U) / ratio;
	if(current > UINT32_MAX) {
		return DRV8874_STATUS_ERROR;
	}
	*current_mA = (uint32_t)current;
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_getCurrentLimit_mA(DRV8874_Object *dev, uint32_t *limit_mA) {
	DRV8874_checkOpen(dev);
	if(limit_mA == NULL) {
		Error_Handler();
	}
	if((dev->config.ipropiResistorOhm == 0U) || (dev->config.vref_mV == 0U)) {
		Error_Handler();
	}
	// The nominal comparator threshold is based on VREF; this is not an OCP threshold.
	const uint64_t ratio = (uint64_t)dev->config.ipropiResistorOhm * DRV8874_AIPROPI_TYP_UA_PER_A;
	const uint64_t current = ((uint64_t)dev->config.vref_mV * 1000000U + ratio / 2U) / ratio;
	if(current > UINT32_MAX) {
		return DRV8874_STATUS_ERROR;
	}
	*limit_mA = (uint32_t)current;
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_setCurrentLimit_mA(DRV8874_Object *dev, uint32_t limit_mA) {
	DRV8874_checkOpen(dev);
	if(limit_mA == 0U) {
		Error_Handler();
	}
	if((dev->config.ipropiResistorOhm == 0U) || (dev->config.vrefMax_mV == 0U)) {
		Error_Handler();
	}

	// VREF(mV) = ITRIP(mA) * R(ohm) * AIPROPI(uA/A) / 1,000,000.
	const uint64_t ratio = (uint64_t)dev->config.ipropiResistorOhm * DRV8874_AIPROPI_TYP_UA_PER_A;
	const uint64_t maximum = (uint64_t)dev->config.vrefMax_mV * 1000000U;
	// Check the bound before multiplying, including for oversized current requests.
	if(limit_mA > maximum / ratio) {
		Error_Handler();
	}
	const uint64_t voltageScaled = (uint64_t)limit_mA * ratio;
	if(voltageScaled < 500000U) {
		Error_Handler();
	}
	const uint32_t voltage_mV = (uint32_t)((voltageScaled + 500000U) / 1000000U);
	const uint64_t period = (uint64_t)__HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1U;
	const uint32_t compare = (uint32_t)((period * voltage_mV +
		dev->config.vrefMax_mV / 2U) / dev->config.vrefMax_mV);
	// Do not silently replace a nonzero current limit with zero VREF.
	if(compare == 0U) {
		Error_Handler();
	}
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL, compare);
	dev->config.vref_mV = voltage_mV;
	return DRV8874_STATUS_OK;
}

// ==============================================================================================
// Diagnostics
// ==============================================================================================

// Called from the application's HAL_GPIO_EXTI_Callback; other EXTI pins are ignored.
void DRV8874_faultIRQHandler(uint16_t GPIO_Pin) {
	if(GPIO_Pin == DRV8874_FAULT_PIN) {
		DRV8874_faultActive = HAL_GPIO_ReadPin(DRV8874_FAULT_PORT,
			DRV8874_FAULT_PIN) == GPIO_PIN_RESET;	// nFAULT is asserted LOW.
	}
}

DRV8874_Status DRV8874_readFault(DRV8874_Object *dev, bool *faultActive) {
	DRV8874_checkOpen(dev);
	if(faultActive == NULL) {
		Error_Handler();
	}
	*faultActive = DRV8874_faultActive;
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_getState(DRV8874_Object *dev, DRV8874_State *state) {
	DRV8874_checkOpen(dev);
	if(state == NULL) {
		Error_Handler();
	}
	*state = dev->state; // Commanded/known software state, not a physical status register.
	return DRV8874_STATUS_OK;
}

DRV8874_Status DRV8874_resetFault(DRV8874_Object *dev) {
	DRV8874_Status status = DRV8874_sleep(dev);
	if(status != DRV8874_STATUS_OK) {
		return status;
	}
	status = DRV8874_wake(dev);
	if(status != DRV8874_STATUS_OK) {
		return status;
	}
	// Verify the physical level after recovery, even if an EXTI request is still pending.
	const bool faultActive = HAL_GPIO_ReadPin(DRV8874_FAULT_PORT,
		DRV8874_FAULT_PIN) == GPIO_PIN_RESET;
	return faultActive ? DRV8874_STATUS_FAULT_ACTIVE : DRV8874_STATUS_OK;
}
