#include "DRV8874.h"

#include "main.h"
#include "tim.h"
#include "../ADC/ADC.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>

// Application misuse is fatal; the project's Error_Handler must never return.
_Noreturn void Error_Handler(void);

// ==============================================================================================
// Road Side hardware - configure CubeMX and the mapping defines in DRV8874.h
// ==============================================================================================

extern TIM_HandleTypeDef DRV8874_PWM_TIMER;

// Variables controlled by Interrupt Handlers
static volatile bool DRV8874_faultActive = false;		// Is the DRV8874 in fault?



// ==============================================================================================
// Private helpers
// ==============================================================================================

// Private helpers prototypes
static void	DRV8874_checkInitialized		(DRV8874_Object *dev);
static void	DRV8874_validateConfig			(void);
static void	DRV8874_validatePwmFrequency	(void);



static void DRV8874_checkInitialized(DRV8874_Object *dev) {
	if(dev == NULL) {
		Error_Handler();
	}
	if(!dev->initialized) {
		Error_Handler();
	}
}

static void DRV8874_validateConfig(void) {
	if(	(DRV8874_CURRENT_MODE >= DRV8874_IMODE_COUNT) 		||	// Check if the current mode is one of the available ones
		(DRV8874_VREF_FULL_SCALE_MV <= 0)					||	// Check if the VREF HIGH Voltage is > 0 is 
		(DRV8874_VREF_FILTER_R_OHM <= 0)					||	// Check if there are valid config for the VREF RC filter
		(DRV8874_VREF_FILTER_C_NF <= 0)						||	// Check if there are valid config for the VREF RC filter
		(DRV8874_VREF_SETTLE_TAU_COUNT <= 0)					// Check if the RC Tau value is valid 
	) {
		Error_Handler();
	}

	DRV8874_validatePwmFrequency();
}

static void DRV8874_validatePwmFrequency(void) {
	TIM_TypeDef *timer = DRV8874_PWM_TIMER.Instance;
	uint32_t clockHz;
	uint32_t apbPrescaler;
	
	// Check if the used timer is one of the STM32G431 timers with at least three 
	// PWM channels (TIM1, TIM2, TIM3, TIM4, TIM8)
	if((timer == TIM1) || (timer == TIM8)) {
		clockHz			= HAL_RCC_GetPCLK2Freq();				// These timers use the APB2 clock source
		apbPrescaler	= READ_BIT(RCC->CFGR, RCC_CFGR_PPRE2);	// Read the PRESCALER of the APB2
	}
	else if((timer == TIM2) || (timer == TIM3) || (timer == TIM4)) {
		clockHz			= HAL_RCC_GetPCLK1Freq();				// These timers use the APB1 clock source
		apbPrescaler	= READ_BIT(RCC->CFGR, RCC_CFGR_PPRE1);	// Read the PRESCALER of the APB1
	}
	else {
		Error_Handler();
	}

	// If there is prescaler in the APB clock, the timer has APB Clock with double frequency (shown in CubeMX)
	if(apbPrescaler != 0) {
		clockHz *= 2;
	}

	// Check if the Timer frequency is compatible with the Maximum frequency that the DRV8874
	// can handle (DRVDRV8874_PWM_MAX_KHZ)
	const uint64_t divider = ((uint64_t)timer->PSC + 1) * ((uint64_t)timer->ARR + 1);	// Prescaler (PSC) * Max Counter Value (ARR)
	const uint64_t freqHz = ((uint64_t)clockHz + divider - 1) / divider;			// ceil(clockHz / divider)
	if(freqHz > (uint64_t)DRV8874_PWM_MAX_KHZ * 1000) {
		Error_Handler();
	}
}

// ==============================================================================================
// Public API
// ==============================================================================================

void DRV8874_init(DRV8874_Object *dev, DRV8874_ControlMode controlMode, DRV8874_PwmOffMode pwmOffMode, uint32_t currentLimit_mA) {
	// NULL check on input pointers
	if(dev == NULL) {
		Error_Handler();
	}

	// Check that the input configuration are known!
	if(	(controlMode >= DRV8874_CONTROL_COUNT) ||
		(pwmOffMode >= DRV8874_PWM_OFF_COUNT)) {
		Error_Handler();
	}

	// Check that the compile time parameters are valid and possible to implement in DRV8874
	DRV8874_validateConfig();

	// Initialize the driver run-time state
	memset(dev, 0, sizeof(*dev));	// Initialize Run-Time state to all 0's
	dev->controlMode	= DRV8874_CONTROL_COUNT;
	dev->pwmOffMode		= pwmOffMode;			// Set the PWM OFF mode as requested
	dev->initialized	= true;

	// Compute the settling time of the VREF (setting time is defined because the PWM generated for 
	// VREF is filtered via an RC filter)
	// tau(ms) = R(ohm) * C(nF) / 1,000,000
	const uint64_t rc_ns = (uint64_t)DRV8874_VREF_FILTER_R_OHM * DRV8874_VREF_FILTER_C_NF;
	const uint64_t settleTime_ms = (uint64_t)DRV8874_VREF_SETTLE_TAU_COUNT * rc_ns;		
	dev->vrefSettle_ms = (uint32_t) ((settleTime_ms + 999999) / 1000000);				// ceil (settleTime_ms / 1000000)

	// Put the DRV8874 in sleep before setting all its control inputs (some inputs are sampled
	// only at wake up after a sleep)
	DRV8874_sleep(dev);		// Wait for the DRV8874 to go to sleep 
	
	// Set the controlMode of the DRVC8874
	// The IN1 and IN2 control pins are set to control the motor in the most neutral way possibile 
	// ("Coast" if possibile, if not "Brake")
	DRV8874_setControlMode(dev, controlMode);	// Set the control mode as requested
	
	// Set the requested current threshold, with the motor still disabled.
	DRV8874_setCurrentLimit_mA(dev, currentLimit_mA);

	// Disable the Timer Enable (Timer does not count, PWM does not work)
	// Timer wil be enabled at wake up time!
	CLEAR_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_CEN);

	// Enable the three PWM to control the output pin
	TIM_CCxChannelCmd(DRV8874_PWM_TIMER.Instance, DRV8874_IN1_EN_CHANNEL, TIM_CCx_ENABLE);
	TIM_CCxChannelCmd(DRV8874_PWM_TIMER.Instance, DRV8874_IN2_PH_CHANNEL, TIM_CCx_ENABLE);
	TIM_CCxChannelCmd(DRV8874_PWM_TIMER.Instance, DRV8874_VREF_CHANNEL, TIM_CCx_ENABLE);
	if(IS_TIM_BREAK_INSTANCE(DRV8874_PWM_TIMER.Instance)) {
		// If the timer has MOE, abilitate it
		__HAL_TIM_MOE_ENABLE(&DRV8874_PWM_TIMER);
	}
	
	// Capture an the startup value of FAULT, Interrupts handles subsequent changes
	// Lock the Interrupts in order to make sure to read the stable state of the fault pin
	const uint32_t interruptMask = lock();
	DRV8874_faultActive = HAL_GPIO_ReadPin(DRV8874_FAULT_PORT, DRV8874_FAULT_PIN) == GPIO_PIN_RESET;
	unlock(interruptMask);
}

void DRV8874_close(DRV8874_Object *dev) {
	// Put the DRV8874 to sleep, basically its safe state
	DRV8874_sleep(dev);

	// Disallow PWM to control the output pins
	TIM_CCxChannelCmd(DRV8874_PWM_TIMER.Instance, DRV8874_IN1_EN_CHANNEL, TIM_CCx_DISABLE);
	TIM_CCxChannelCmd(DRV8874_PWM_TIMER.Instance, DRV8874_IN2_PH_CHANNEL, TIM_CCx_DISABLE);
	TIM_CCxChannelCmd(DRV8874_PWM_TIMER.Instance, DRV8874_VREF_CHANNEL, TIM_CCx_DISABLE);
	if(IS_TIM_BREAK_INSTANCE(DRV8874_PWM_TIMER.Instance)) {
		// If the timer has MOE, disabilitate it
		__HAL_TIM_MOE_DISABLE(&DRV8874_PWM_TIMER);
	}

	// Reset the RunTime state of the Driver!
	memset(dev, 0, sizeof(*dev));
}

void DRV8874_sleep(DRV8874_Object *dev) {
	DRV8874_checkInitialized(dev);
	
	// Set the Sleep Pin to Sleep Mode and wait the datasheet required delay
	HAL_GPIO_WritePin(DRV8874_SLEEP_PORT, DRV8874_SLEEP_PIN, GPIO_PIN_RESET);
	dev->isAwake = false;
	HAL_Delay(DRV8874_SLEEP_DELAY_MS);

	// Pause the Timer without changing its current configuration and state
	CLEAR_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_CEN);
}

void DRV8874_wake(DRV8874_Object *dev) {
	DRV8874_checkInitialized(dev);
	if(dev->isAwake) {
		return;
	}

	// Start the Timer without changing its current configuration and state
	SET_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_CEN);
	
	// Let the RC filter settle before enabling the H-bridge (because the RC is controlled
	// by the Timer, which is just been turned on)
	if(dev->vrefSettle_ms != 0) {
		HAL_Delay(dev->vrefSettle_ms);
	}

	// Wake up the DRV8874 and wait for the required delay
	HAL_GPIO_WritePin(DRV8874_SLEEP_PORT, DRV8874_SLEEP_PIN, GPIO_PIN_SET);
	HAL_Delay(DRV8874_WAKE_DELAY_MS);
	dev->isAwake = true;
}

void DRV8874_setControlMode(DRV8874_Object *dev, DRV8874_ControlMode mode) {
	DRV8874_checkInitialized(dev);
	if(mode >= DRV8874_CONTROL_COUNT) {
		Error_Handler();
	}

	if(mode == dev->controlMode) {
		return;
	}

	// If the DRV8874 was NOT sleeping, put it to sleep, modify the control mode, and
	// then wake it up again (the Control Mode input is sampled ONLY at wake up time!)
	const bool wasAwake = dev->isAwake;
	if(wasAwake) {
		DRV8874_sleep(dev);
	}

	switch (mode) {
		case DRV8874_CONTROL_PH_EN:
			HAL_GPIO_WritePin	(DRV8874_PMODE_PORT, DRV8874_PMODE_PIN, GPIO_PIN_RESET);
			break;

		case DRV8874_CONTROL_IN_IN:
			HAL_GPIO_WritePin	(DRV8874_PMODE_PORT, DRV8874_PMODE_PIN, GPIO_PIN_SET);
			break;

		default:
			Error_Handler();
			break;
	}
	dev->controlMode = mode;

	// Set the behaviour of the DRV8874 after wake up (start with the most neutral state,
	// brake in PH/EN mode and Coast in PWM mode)
	if(dev->controlMode == DRV8874_CONTROL_PH_EN) {
		DRV8874_brake(dev);
	}
	else {
		DRV8874_coast(dev);
	}

	// Wake up the DRV8874 if it was awake before the Mode change
	if(wasAwake) {
		DRV8874_wake(dev);
	}
}


void DRV8874_setDutyCycle(DRV8874_Object *dev, int16_t dutyPermille) {
	DRV8874_checkInitialized(dev);
	if((dutyPermille < -1000) || (dutyPermille > 1000)) {
		Error_Handler();
	}
	if(!dev->isAwake) {
		Error_Handler();
	}
	
	uint16_t dutyPermulleAbs;
	if(dutyPermille < 0) {
		dutyPermulleAbs = (uint16_t)(-dutyPermille);
	}
	else {
		dutyPermulleAbs = (uint16_t)dutyPermille;
	}
	const bool isForward		= dutyPermille >= 0;
	const uint32_t period	= __HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1;			// Total tick count of the period
	const uint32_t compare	= (uint32_t)(((uint64_t)period * dutyPermulleAbs) / 1000);	// Total tick in which CNT < CCR --> Output High! 

	// Now apply the new Duty Cycle to the H-Bridge. PWM must be applied to IN1 or IN2 based on the Control
	// Mode I'm in, and on the direction requested for the motor (Forward or Reverse)
	
	// Beacuse preload is active (selected in CubeMX), the newly selected states and Duty Cycle are applied
	// only at start of a new PWM cycle. In order to avoid mis-alignments between the signals, keep the 
	// previous PWM selection active until I preloaded BOTH PWM (basically keep UIDS = 1, so data in PWM
	// can be updated but will not be applied)
	SET_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_UDIS);
	
	switch (dev->controlMode) {
		case DRV8874_CONTROL_PH_EN:
			if(isForward) {
				// Set always PH = HIGH	--> Motor forward
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, period);
			}
			else {
				// Set always PH = LOW	--> Motor Reverse
				__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, 0);
			}
			// Set the PWM Duty Cycle to EN pin (basically the Motor is controlled in Brake/Forward or
			// Brake/Reverse PWM regime)
			__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, compare);
			break;

		case DRV8874_CONTROL_IN_IN:
			if(dev->pwmOffMode == DRV8874_PWM_OFF_COAST) {
				if(isForward) {
					// To move forward, with Coast PWM --> IN2 = LOW, IN1 = PWM
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, 0);
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, compare);
				}
				else {
					// To move reverse, with Coast PWM --> IN1 = LOW, IN2 = PWM
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, 0);
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, compare);
				}
			}
			else {
				// In the case of Brake when PWM Off, when PWM = HIGH the motor is braking, which is the opposite 
				// of the PWM control I expect
				// Compute 100% − duty richiesto to get the correct Duty Cycle to apply to PWM
				const uint32_t inverse = (uint32_t)(((uint64_t)period * (1000 - dutyPermulleAbs)) / 1000);
				
				if(isForward) {
					// To move forward, with Brake PWM --> IN1 = HIGH, IN2 = PWM
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, period);
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, inverse);
				}
				else {
					// To move reverse, with Brake PWM --> IN1 = LOW, IN2 = HIGH
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, period);
					__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, inverse);
				}
			}
			break;

		default:
			Error_Handler();
			break;
	}

	// Apply the PWM configuration changes at the start of the next PWM cycle (UDI0S = 0)
	CLEAR_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_UDIS);
}

void DRV8874_forward(DRV8874_Object *dev) {
	DRV8874_setDutyCycle(dev, 1000);
}

void DRV8874_reverse(DRV8874_Object *dev) {
	DRV8874_setDutyCycle(dev, -1000);
}

void DRV8874_brake(DRV8874_Object *dev) {
	DRV8874_checkInitialized(dev);

	// Avoid the application of Preload to PWM Peripheral
	SET_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_UDIS);

	if(dev->controlMode == DRV8874_CONTROL_PH_EN) {
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, 0);
	}
	else {
		const uint32_t period = __HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1;
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, period);
		__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, period);
	}

	// Allow the application of Preload to PWM Peripheral at the start of next PWM Cycle
	CLEAR_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_UDIS);
}


void DRV8874_coast(DRV8874_Object *dev) {
	DRV8874_checkInitialized(dev);
	
	// Coast is only possible in the PWM Control Mode (IN1/IN2)
	if(dev->controlMode != DRV8874_CONTROL_IN_IN) {
		Error_Handler();
	}

	// Avoid the application of Preload to PWM Peripheral
	SET_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_UDIS);
	
	// Coast in PWM Mode --> IN1 = 0, IN2 = 0
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, 0);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, 0);
	
	// Allow the application of Preload to PWM Peripheral at the start of next PWM Cycle
	CLEAR_BIT(DRV8874_PWM_TIMER.Instance->CR1, TIM_CR1_UDIS);
}


bool DRV8874_readCurrent_mA(DRV8874_Object *dev, uint32_t *current_mA) {
	DRV8874_checkInitialized(dev);
	if(current_mA == NULL) {
		Error_Handler();
	}
	if((DRV8874_IPROPI_RESISTOR_OHM == 0)) {
		Error_Handler();
	}
	if(!dev->isAwake) {
		Error_Handler();
	}
	if((dev->controlMode == DRV8874_CONTROL_IN_IN) &&
		(__HAL_TIM_GET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL) == 0) &&
		(__HAL_TIM_GET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL) == 0)) {
		return false;
	}

	uint32_t voltage_mV;
	const ADC_Status adcStatus = ADC_readVoltage_mV(&DRV8874_IPROPI_ADC,
		DRV8874_IPROPI_ADC_CHANNEL, &voltage_mV);
	if((adcStatus == ADC_STATUS_BUSY) || (adcStatus == ADC_STATUS_NOT_READY)) {
		return false;
	}
	if(adcStatus != ADC_STATUS_OK) {
		DRV8874_sleep(dev);
		Error_Handler();
	}
	// I(A) = V(V) / (R(ohm) * AIPROPI(A/A)). Return nonnegative current in mA.
	// This is an estimate, affected by mirror accuracy and possible VREF clamping.
	const uint64_t ratio = (uint64_t)DRV8874_IPROPI_RESISTOR_OHM * DRV8874_AIPROPI_TYP_UA_PER_A;
	const uint64_t current = ((uint64_t)voltage_mV * 1000000 + ratio / 2) / ratio;
	if(current > UINT32_MAX) {
		DRV8874_sleep(dev);
		Error_Handler();
	}
	*current_mA = (uint32_t)current;
	return true;
}

void DRV8874_setCurrentLimit_mA(DRV8874_Object *dev, uint32_t limit_mA) {
	DRV8874_checkInitialized(dev);
	if(limit_mA == 0) {
		Error_Handler();
	}
	if((DRV8874_IPROPI_RESISTOR_OHM == 0) || (DRV8874_VREF_FULL_SCALE_MV == 0)) {
		Error_Handler();
	}

	// VREF(mV) = ITRIP(mA) * R(ohm) * AIPROPI(uA/A) / 1,000,000.
	const uint64_t ratio = (uint64_t)DRV8874_IPROPI_RESISTOR_OHM * DRV8874_AIPROPI_TYP_UA_PER_A;
	const uint64_t maximum = (uint64_t)DRV8874_VREF_FULL_SCALE_MV * 1000000;
	
	// Check the bound before multiplying, including for oversized current requests.
	uint64_t voltageScaled;
	if(limit_mA > maximum / ratio) {
		voltageScaled = maximum;
	}
	else {
		voltageScaled = (uint64_t)limit_mA * ratio;
	}
	if(voltageScaled < 500000) {
		Error_Handler();
	}
	const uint32_t voltage_mV = (uint32_t)((voltageScaled + 500000) / 1000000);
	const uint64_t period = (uint64_t)__HAL_TIM_GET_AUTORELOAD(&DRV8874_PWM_TIMER) + 1;
	const uint32_t compare = (uint32_t)((period * voltage_mV +
		DRV8874_VREF_FULL_SCALE_MV / 2) / DRV8874_VREF_FULL_SCALE_MV);
	// Do not silently replace a nonzero current limit with zero VREF.\	
		Error_Handler();
	}
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_VREF_CHANNEL, compare);
}


// Called from the application's HAL_GPIO_EXTI_Callback; other EXTI pins are ignored.
void DRV8874_faultIRQHandler(uint16_t GPIO_Pin) {
	if(GPIO_Pin == DRV8874_FAULT_PIN) {
		DRV8874_faultActive = HAL_GPIO_ReadPin(DRV8874_FAULT_PORT,
			DRV8874_FAULT_PIN) == GPIO_PIN_RESET;	// nFAULT is asserted LOW.
	}
}

bool DRV8874_isFaultActive(DRV8874_Object *dev) {
	DRV8874_checkInitialized(dev);
	return DRV8874_faultActive;
}

void DRV8874_resetFault(DRV8874_Object *dev) {
	DRV8874_checkInitialized(dev);
	
	// Fault can be manually resetted ONLY IF the DRV8874 mode is Latching the fault
	// In other case DRV8874 automatically re-tries to reset fault autonusly
	if(	(DRV8874_CURRENT_MODE != DRV8874_IMODE_FIXED_LATCH) &&
		(DRV8874_CURRENT_MODE != DRV8874_IMODE_CBC_LATCH)) {
		Error_Handler();
	}

	//
	DRV8874_sleep(dev);

	// Recovery does not automatically resume the previous motor command.
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN1_EN_CHANNEL, 0);
	__HAL_TIM_SET_COMPARE(&DRV8874_PWM_TIMER, DRV8874_IN2_PH_CHANNEL, 0);
	DRV8874_wake(dev);
}
