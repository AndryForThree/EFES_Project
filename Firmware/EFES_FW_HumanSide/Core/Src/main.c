/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "dma.h"
#include "spi.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "st7789.h"
#include "st7789_transport.h"
#include "UI_module.h"
#include "App.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
/* Independent simulated data sources. UI refresh remains owned by TIM6. */
#define DEMO_ANGLE_PERIOD_MS 10U
#define DEMO_SPEED_PERIOD_MS 100U
#define DEMO_STATUS_PERIOD_MS 250U
#define DEMO_CYCLE_MS 40000U

static const struct {
  uint32_t time_ms;
  int16_t angle_deci_deg;
  uint16_t speed_kmh;
} demo_route[] = {
  /* Time     Steering   Speed: acceleration, bends, then parking. */
  {    0,       0,        0},
  { 5000,       0,       45},
  { 9000,      60,       55},
  {13000,     -60,       55},
  {17000,       0,       35},
  {21000,     300,       18},
  {25000,    -450,        8},
  {29000,    4500,        5},
  {33000,   -4500,        5},
  {37000,       0,        0},
  {40000,       0,        0}
};

/* Dedicated road-wheel targets in tenths of a degree, one step every 5 s. */
static const int16_t demo_road_targets[] = {0, 124, -160, 60, -30, 200, -200, 0};
/* Response time in 10 ms steps: COMFORT 250 ms, ECO 450 ms, SPORT 100 ms. */
static const int demo_motor_response_steps[] = {
  [UI_DRIVE_NORMAL] = 25, [UI_DRIVE_ECO] = 45, [UI_DRIVE_SPORT] = 10
};
static int16_t demo_motor_angle;
static UI_State demo_state;
static uint32_t demo_started_at;
static uint32_t demo_angle_at;
static uint32_t demo_speed_at;
static uint32_t demo_status_at;

static int32_t Demo_Interpolate(int32_t from, int32_t to,
                                uint32_t elapsed, uint32_t duration)
{
  return from + (to - from) * (int32_t)elapsed / (int32_t)duration;
}

static void Demo_Init(void)
{
  uint32_t now = HAL_GetTick();
  demo_started_at = now;
  demo_angle_at = now;
  demo_speed_at = now;
  demo_status_at = now;
  demo_motor_angle = 0;
  demo_state = (UI_State){
    .drive_mode = UI_DRIVE_NORMAL,
    .road_feedback_received_at_ms = now,
    .road_feedback_valid = true,
    .sensor_sample_received_at_ms = now,
    .channel_b_angle_deci_deg = 1,
    .sensor_deviation_limit_deci_deg = 10, /* Temporary simulated FPGA configuration. */
    .channel_a_valid = true,
    .channel_b_valid = true,
    .steering_ratio_deci = 128,
    .sensors_valid = true,
    .can_online = true,
    .actuator_ready = true,
    .speed_simulated = true
  };
  UI_SetState(&demo_state);
}

static void Demo_Process(void)
{
  uint32_t now = HAL_GetTick();
  bool angle_due = (uint32_t)(now - demo_angle_at) >= DEMO_ANGLE_PERIOD_MS;
  bool speed_due = (uint32_t)(now - demo_speed_at) >= DEMO_SPEED_PERIOD_MS;
  bool status_due = (uint32_t)(now - demo_status_at) >= DEMO_STATUS_PERIOD_MS;
  if (!angle_due && !speed_due && !status_due) return;

  uint32_t phase = (uint32_t)(now - demo_started_at) % DEMO_CYCLE_MS;
  unsigned segment = 0;
  while (phase >= demo_route[segment + 1].time_ms) segment++;
  uint32_t elapsed = phase - demo_route[segment].time_ms;
  uint32_t duration = demo_route[segment + 1].time_ms - demo_route[segment].time_ms;

  if (angle_due) {
    demo_angle_at = now;
    demo_state.steering_angle_deci_deg = Demo_Interpolate(
      demo_route[segment].angle_deci_deg, demo_route[segment + 1].angle_deci_deg,
      elapsed, duration);
    int offset = 1 + (phase / 250U) % 4U;
    if (phase >= 26000U && phase < 28000U)
      offset = 4 + (phase - 26000U) / 200U;
    if (phase >= 28000U && phase < 32000U) offset = 14;
    /* Simulated sensor silence: other modules keep publishing their own data. */
    if (!(phase >= 20000U && phase < 23000U)) {
      demo_state.channel_a_angle_deci_deg = demo_state.steering_angle_deci_deg;
      demo_state.channel_b_angle_deci_deg = demo_state.channel_a_angle_deci_deg + offset;
      demo_state.sensor_sample_received_at_ms = now;
    }
    demo_state.road_requested_angle_deci_deg = demo_road_targets[phase / 5000U];
    /* Mode changes only the simulated motor response, not the UI timings. */
    int motor_error = demo_state.road_requested_angle_deci_deg - demo_motor_angle;
    int response_steps = demo_motor_response_steps[demo_state.drive_mode];
    demo_motor_angle += motor_error >= 0 ? (motor_error + response_steps - 1) / response_steps :
                                          (motor_error - response_steps + 1) / response_steps;
    /* Simulate CAN feedback silence from 18 to 20 s; the motor keeps moving. */
    if (!(phase >= 18000U && phase < 20000U) && !(phase >= 38000U && phase < 39000U)) {
      demo_state.road_actual_angle_deci_deg = demo_motor_angle;
      demo_state.road_feedback_received_at_ms = now;
    }
  }
  if (speed_due) {
    demo_speed_at = now;
    demo_state.vehicle_speed_kmh = Demo_Interpolate(
      demo_route[segment].speed_kmh, demo_route[segment + 1].speed_kmh,
      elapsed, duration);
    /* Example speed-adaptive map: 12.0:1 at rest, 13.1:1 at 55 km/h. */
    demo_state.steering_ratio_deci = 120U + demo_state.vehicle_speed_kmh / 5U;
  }
  if (status_due) {
    demo_status_at = now;
    /* Ten seconds per mode, using the data clock rather than the UI timer. */
    demo_state.drive_mode = (UI_DriveMode)(((uint32_t)(now - demo_started_at) / 10000U) % 3U);
    /* Brief diagnostic changes while stopped, then automatic recovery.
     * Keep alarms zero: the separate alarm page is still empty.
     */
    /* Simulate an incoming hardware flag independently of the measured delta.
     * From 27.4 s to 28 s the bar saturates but stays green until that flag arrives.
     */
    demo_state.sensor_plausibility_fault = phase >= 28000U && phase < 32000U;
    demo_state.channel_a_valid = true;
    demo_state.channel_b_valid = !(phase >= 37000U && phase < 38000U);
    demo_state.sensors_valid = demo_state.channel_a_valid && demo_state.channel_b_valid &&
                               !demo_state.sensor_plausibility_fault;
    demo_state.can_online = !(phase >= 38000U && phase < 39000U);
    demo_state.road_feedback_valid = phase < 39000U;
    demo_state.actuator_ready = !(phase >= 39000U);
  }

  /* Publish the latest data once, without waiting for the display. If the
   * superloop is late, sample the current route time instead of replaying it.
   */
  UI_SetState(&demo_state);
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_SPI1_Init();
  /* USER CODE BEGIN 2 */
  if (ST7789_Init() != ST7789_OK) {
    Error_Handler();
  }
  UI_Init();

  Demo_Init();
  App_Init();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    App_Process();
    Demo_Process();
    ST7789_Process();
    UI_Process();
    if (ST7789_GetState() == ST7789_STATE_ERROR) {
      HAL_GPIO_WritePin(Board_LED_GPIO_Port, Board_LED_Pin, GPIO_PIN_SET);
    }
    /* Other modules will run here. */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV1;
  RCC_OscInitStruct.PLL.PLLN = 42;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV4;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi)
{
  ST7789_TransportTxCompleteISR(hspi);
}

void HAL_SPI_ErrorCallback(SPI_HandleTypeDef *hspi)
{
  ST7789_TransportErrorISR(hspi);
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
