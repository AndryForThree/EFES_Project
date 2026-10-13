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
#include <stdio.h>

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
/* Observe in the debugger: elapsed time of the latest full-screen fill. */
volatile uint32_t display_last_fill_ms;
static volatile ST7789_Result display_last_result;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
/* Strings passed to the async renderer must survive until completion. */
static char display_time_text[48];
static char display_buffer_text[48];

static ST7789_Result DisplayDemo_Start(uint8_t step)
{
    switch (step) {
    case 0: return ST7789_Fill_Color(RED);
    case 1: return ST7789_Fill_Color(GREEN);
    case 2: return ST7789_Fill_Color(BLUE);
    case 3: return ST7789_Fill_Color(BLACK);
    case 4: return ST7789_FillHorizontalGradient(MAGENTA, BLACK);
    case 5: return ST7789_Fill_Color(BLACK);
    case 6: return ST7789_DrawRectangle(0, 0, ST7789_WIDTH - 1, ST7789_HEIGHT - 1, WHITE);
    case 7: return ST7789_WriteString(10, 10, "EFES - DMA test", Font_11x18, WHITE, BLACK);
    case 8: return ST7789_WriteString(10, 40, "320x240 - Landscape", Font_7x10, WHITE, BLACK);
    case 9: return ST7789_DrawFilledRectangle(10, 70, 100, 70, RED);
    case 10: return ST7789_DrawFilledRectangle(110, 70, 100, 70, GREEN);
    case 11: return ST7789_DrawFilledRectangle(210, 70, 100, 70, BLUE);
    case 12: return ST7789_WriteString(10, 150, "RED", Font_7x10, WHITE, BLACK);
    case 13: return ST7789_WriteString(110, 150, "GREEN", Font_7x10, WHITE, BLACK);
    case 14: return ST7789_WriteString(210, 150, "BLUE", Font_7x10, WHITE, BLACK);
    case 15: return ST7789_WriteString(10, 220, "BOTTOM LEFT", Font_7x10, WHITE, BLACK);
    case 16: return ST7789_WriteString(225, 220, "BOTTOM RIGHT", Font_7x10, WHITE, BLACK);
    case 17: return ST7789_DrawCircle(260, 185, 18, YELLOW);
    case 18: return ST7789_DrawFilledCircle(220, 185, 12, GREEN);
    case 19: return ST7789_DrawTriangle(160, 170, 190, 200, 150, 200, WHITE);
    case 20: return ST7789_DrawLine(10, 165, 309, 165, WHITE);
    case 21: return ST7789_DrawFilledTriangle(170, 205, 190, 205, 180, 215, BLUE);
    case 22: return ST7789_Fill(290, 180, 309, 199, WHITE);
    case 23: return ST7789_Fill(290, 180, 309, 199, BLACK);
    default: return ST7789_INVALID_ARGUMENT;
    }
}

static void DisplayDemo_Process(void)
{
    enum { REQUEST, WAIT_DRAW, REQUEST_TIME, WAIT_TIME,
           REQUEST_BUFFER, WAIT_BUFFER, HOLD };
    static uint8_t step, phase;
    static uint32_t started_at, completed_at;
    uint32_t now = HAL_GetTick();

    if (ST7789_GetState() == ST7789_STATE_ERROR) {
        HAL_GPIO_WritePin(Board_LED_GPIO_Port, Board_LED_Pin, GPIO_PIN_SET);
        return;
    }
    if (ST7789_GetState() != ST7789_STATE_IDLE) return;
    switch (phase) {
    case REQUEST:
        started_at = now;
        display_last_result = DisplayDemo_Start(step);
        if (display_last_result == ST7789_OK) phase = WAIT_DRAW;
        break;
    case WAIT_DRAW:
        if (step <= 3) {
            static const char *const names[] = { "RED", "GREEN", "BLUE", "BLACK" };
            /* End timing before scheduling either of the result strings. */
            display_last_fill_ms = now - started_at;
            snprintf(display_time_text, sizeof(display_time_text), "%s: %lu ms",
                     names[step], (unsigned long)display_last_fill_ms);
            snprintf(display_buffer_text, sizeof(display_buffer_text), "Buffer: %lu px",
                     (unsigned long)ST7789_BUFFER_PIXELS);
            phase = REQUEST_TIME;
        } else {
            completed_at = now;
            phase = HOLD;
        }
        break;
    case REQUEST_TIME:
        display_last_result = ST7789_WriteString(10, 180, display_time_text,
                                                 Font_11x18, WHITE, BLACK);
        if (display_last_result == ST7789_OK) phase = WAIT_TIME;
        break;
    case WAIT_TIME:
        phase = REQUEST_BUFFER;
        break;
    case REQUEST_BUFFER:
        display_last_result = ST7789_WriteString(10, 200, display_buffer_text,
                                                 Font_7x10, WHITE, BLACK);
        if (display_last_result == ST7789_OK) phase = WAIT_BUFFER;
        break;
    case WAIT_BUFFER:
        completed_at = now;
        phase = HOLD;
        break;
    case HOLD: {
        uint32_t hold_ms = step <= 3 ? 1000U :
                           (step == 4 ? 2000U : (step >= 22 ? 500U : 0U));
        if ((uint32_t)(now - completed_at) < hold_ms) break;
        step++;
        if (step == 24) step = 22;
        phase = REQUEST;
        break;
    }
    default: break;
    }
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
  display_last_result = ST7789_Init();
  if (display_last_result != ST7789_OK) {
    Error_Handler();
  }

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    ST7789_Process();
    DisplayDemo_Process();
    /* Other application work can run here while DMA sends prepared pixels. */
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
  RCC_OscInitStruct.PLL.PLLN = 40;
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
