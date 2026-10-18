#include "UI_timer.h"
#include "main.h"

/* TIM6 counts at 10 kHz: 10 ticks per ms, up to 6553 ms per period.
 * The hardware stays here; UI_module.c only uses the timer API.
 */
static volatile bool elapsed;

void UI_Timer_Init(uint16_t period_ms)
{
    RCC_ClkInitTypeDef clocks;
    uint32_t flash_latency;
    uint32_t timer_clock = HAL_RCC_GetPCLK1Freq();

    HAL_RCC_GetClockConfig(&clocks, &flash_latency);
    if (clocks.APB1CLKDivider != RCC_HCLK_DIV1) timer_clock *= 2U;

    __HAL_RCC_TIM6_CLK_ENABLE();
    TIM6->CR1 = TIM_CR1_URS;
    TIM6->DIER = 0;
    TIM6->PSC = timer_clock / 10000U - 1U;
    UI_Timer_SetPeriod(period_ms);
    TIM6->DIER = TIM_DIER_UIE;

    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 6, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
}

void UI_Timer_Enable(void)
{
    TIM6->CR1 |= TIM_CR1_CEN;
}

void UI_Timer_Disable(void)
{
    TIM6->CR1 &= ~TIM_CR1_CEN;
}

void UI_Timer_Reset(void)
{
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    TIM6->EGR = TIM_EGR_UG;
    TIM6->SR = 0;
    HAL_NVIC_ClearPendingIRQ(TIM6_DAC_IRQn);
    elapsed = false;
    __set_PRIMASK(mask);
}

bool UI_Timer_SetPeriod(uint16_t period_ms)
{
    uint32_t running;

    if (period_ms == 0 || period_ms > 6553U) return false;

    running = TIM6->CR1 & TIM_CR1_CEN;
    UI_Timer_Disable();
    TIM6->ARR = (uint32_t)period_ms * 10U - 1U;
    UI_Timer_Reset();
    if (running != 0) UI_Timer_Enable();
    return true;
}

bool UI_Timer_TakeElapsed(void)
{
    bool result;
    uint32_t mask = __get_PRIMASK();

    /* Consume the flag without losing an interrupt between read and clear. */
    __disable_irq();
    result = elapsed;
    elapsed = false;
    __set_PRIMASK(mask);
    return result;
}

void TIM6_DAC_IRQHandler(void)
{
    TIM6->SR = 0;
    elapsed = true;
}
