#ifndef EFES_ADC_H_
#define EFES_ADC_H_

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Contract for the future ADC service; no implementation is provided yet.
 * The service owns CubeMX/HAL handles, calibration, acquisition, resolution,
 * data alignment and VREFINT measurements. Devices sharing a physical voltage
 * reference share its measured value, but retain their own conversion settings.
 * Application startup initializes the service before any peripheral uses it.
 */
typedef struct ADC_Device ADC_Device;
extern ADC_Device ADC_device1;

typedef enum {
	ADC_STATUS_OK,
	ADC_STATUS_BUSY,
	ADC_STATUS_NOT_READY,
	ADC_STATUS_ERROR
} ADC_Status;

typedef struct {
	uint32_t voltage_mV;
	bool valid;
} ADC_ReferenceInfo;

/* Returns a coherent copy of the shared reference information for this device.
 * The ADC service alone updates the underlying state. No acquisition is started.
 */
ADC_Status ADC_getReferenceInfo(ADC_Device *dev, ADC_ReferenceInfo *info);

/* Requests and reads a fresh sample of the selected physical channel.
 * channel is the channel number (e.g. 1 for ADC1_IN1), not a HAL encoding.
 * Blocking, with a bounded timeout managed by the service; call outside ISRs.
 * The service arbitrates shared ADC use and preserves other users' configuration.
 * It converts the result to mV using its resolution and measured reference.
 * BUSY: device in use; NOT_READY: service/reference not yet valid;
 * ERROR: acquisition/conversion failure, including timeout.
 * Writes voltage_mV only on OK; never returns an old cached channel sample.
 */
ADC_Status ADC_readVoltage_mV(ADC_Device *dev, uint32_t channel, uint32_t *voltage_mV);

#ifdef __cplusplus
}
#endif

#endif
