#include "App.h"
#include "main.h"
#include "UI_module.h"

#define APP_BUTTON_PRESSED GPIO_PIN_SET /* PC13 pull-down; press observed as high. */
#define APP_BUTTON_DEBOUNCE_MS 30U

static GPIO_PinState button_raw;
static GPIO_PinState button_stable;
static uint32_t button_changed_at;

void App_Init(void)
{
    button_raw = HAL_GPIO_ReadPin(USER_Button_GPIO_Port, USER_Button_Pin);
    button_stable = button_raw;
    button_changed_at = HAL_GetTick();
}

void App_Process(void)
{
    uint32_t now = HAL_GetTick();
    GPIO_PinState level = HAL_GPIO_ReadPin(USER_Button_GPIO_Port, USER_Button_Pin);

    if (level != button_raw) {
        button_raw = level;
        button_changed_at = now;
    }

    if (button_raw != button_stable &&
        (uint32_t)(now - button_changed_at) >= APP_BUTTON_DEBOUNCE_MS) {
        button_stable = button_raw;
        if (button_stable == APP_BUTTON_PRESSED)
            UI_PostEvent(UI_EVENT_NEXT_PAGE);
    }
}
