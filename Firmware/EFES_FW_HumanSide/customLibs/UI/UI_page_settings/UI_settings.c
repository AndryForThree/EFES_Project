#include "UI_settings.h"
#include "UI_private.h"
#include "st7789.h"
#include <stdio.h>

#define SETTINGS_VISIBLE_ITEMS	4U
#define SETTINGS_ROW_HEIGHT		34U

typedef struct {
	App_View drawn_view;
	bool first_frame;
	uint8_t step;
	uint8_t row;
	uint8_t row_step;
	char text[96];
	char path[96];
} UI_SettingsContext;

static UI_SettingsContext settings;

static bool ViewChanged(const App_View *view)
{
	return settings.first_frame || view->menu != settings.drawn_view.menu ||
		view->menu_mode != settings.drawn_view.menu_mode ||
		view->selected_item != settings.drawn_view.selected_item ||
		view->edit_value != settings.drawn_view.edit_value ||
		view->confirm_ok != settings.drawn_view.confirm_ok;
}

static void FormatMenuPath(const App_Menu *menu)
{
	settings.path[0] = '\0';
	while (menu != NULL) {
		if (settings.path[0] == '\0') {
			snprintf(settings.text, sizeof(settings.text), "%s", menu->title);
		} else {
			snprintf(settings.text, sizeof(settings.text), "%s > %s", menu->title, settings.path);
		}
		snprintf(settings.path, sizeof(settings.path), "%s", settings.text);
		menu = menu->parent;
	}
}

static ST7789_Result WritePanelLine(uint16_t y, const char *text, FontId font, uint16_t color)
{
	return ST7789_WriteTextField(24, y, 272, text, font,
		ST7789_TEXT_CENTER, color, UI_CARD_BACKGROUND);
}

static bool ProcessList(const App_View *view)
{
	uint8_t first_item = view->selected_item / SETTINGS_VISIBLE_ITEMS * SETTINGS_VISIBLE_ITEMS;
	uint8_t index = first_item + settings.row;
	if (settings.row == SETTINGS_VISIBLE_ITEMS || index >= view->menu->item_count) return true;

	const App_MenuItem *item = &view->menu->items[index];
	bool selected = index == view->selected_item;
	uint16_t background = selected ? UI_SELECTION_COLOR : UI_CARD_BACKGROUND;
	uint16_t y = 52 + settings.row * SETTINGS_ROW_HEIGHT;
	ST7789_Result result = ST7789_OK;

	switch (settings.row_step) {
		case 0:
			result = ST7789_DrawRoundedRectangle(12, y, 296, 30, 5,
				selected ? UI_ACCENT_COLOR : UI_BORDER_COLOR, background, UI_BACKGROUND);
			break;
		case 1:
			if (selected) {
				result = ST7789_DrawFilledRectangle(13, y + 8, 3, 14, UI_ACCENT_COLOR);
			}
			break;
		case 2: {
			const char *label = item->label;
			if (item->type == APP_ITEM_SUBMENU) label = item->submenu->title;
			result = ST7789_WriteTextField(24, y + 7, 216, label,
				FONT_INTER_MEDIUM_12, ST7789_TEXT_LEFT, UI_TEXT_COLOR, background);
			break;
		}
		case 3: {
			const char *hint = ">";
			if (item->type == APP_ITEM_PARAMETER) hint = "EDIT";
			if (item->type == APP_ITEM_ACTION) hint = item->action != NULL ? "RUN" : "";
			result = ST7789_WriteTextField(248, y + 9, 48, hint,
				FONT_INTER_MEDIUM_10, ST7789_TEXT_RIGHT,
				selected ? UI_ACCENT_COLOR : UI_MUTED_COLOR, background);
			break;
		}
		default:
			settings.row++;
			settings.row_step = 0;
			return false;
	}

	if (result == ST7789_OK) settings.row_step++;
	return false;
}

void UI_Settings_Reset(void)
{
	settings.first_frame = true;
	settings.step = 0;
	settings.row = 0;
	settings.row_step = 0;
}

bool UI_Settings_Process(const App_View *view)
{
	if (ST7789_GetState() != ST7789_STATE_IDLE) return false;

	const App_Menu *menu = view->menu;
	const App_MenuItem *item = &menu->items[view->selected_item];
	bool list = view->menu_mode == APP_MENU_LIST;
	bool closed = view->menu_mode == APP_MENU_CLOSED;
	ST7789_Result result = ST7789_OK;

	switch (settings.step) {
		case 0:
			if (!ViewChanged(view)) return true;
			FormatMenuPath(menu);
			settings.row = 0;
			settings.row_step = 0;
			result = ST7789_DrawFilledRectangle(0, 23, 320, 217, UI_BACKGROUND);
			break;
		case 1:
			result = ST7789_WriteTextField(12, 31, 248, settings.path,
				FONT_INTER_MEDIUM_10, ST7789_TEXT_LEFT, UI_MUTED_COLOR, UI_BACKGROUND);
			break;
		case 2:
			if (list) {
				snprintf(settings.text, sizeof(settings.text), "%u / %u",
					(unsigned)view->selected_item + 1U, (unsigned)menu->item_count);
				result = ST7789_WriteTextField(264, 31, 44, settings.text,
					FONT_INTER_MEDIUM_10, ST7789_TEXT_RIGHT, UI_ACCENT_COLOR, UI_BACKGROUND);
			}
			break;
		case 3:
			if (!list) {
				result = ST7789_DrawRoundedRectangle(12, 52, 296, 140, 6,
					UI_BORDER_COLOR, UI_CARD_BACKGROUND, UI_BACKGROUND);
			}
			break;
		case 4:
			if (list && !ProcessList(view)) return false;
			break;
		case 5:
			if (!list) {
				result = WritePanelLine(65, closed ? menu->title : item->label,
					FONT_INTER_BOLD_14, UI_ACCENT_COLOR);
			}
			break;
		case 6:
			if (!list) {
				result = ST7789_DrawFilledRectangle(24, 90, 272, 1, UI_BORDER_COLOR);
			}
			break;
		case 7:
			switch (view->menu_mode) {
				case APP_MENU_CLOSED:
					result = WritePanelLine(108, "Press OK to open the menu",
						FONT_INTER_MEDIUM_12, UI_TEXT_COLOR);
					break;
				case APP_MENU_EDIT:
					snprintf(settings.text, sizeof(settings.text), "%ld", (long)view->edit_value);
					result = WritePanelLine(101, settings.text, FONT_RAJDHANI_SEMIBOLD_28, UI_TEXT_COLOR);
					break;
				case APP_MENU_CONFIRM:
					result = WritePanelLine(105, "Start this procedure?",
						FONT_INTER_MEDIUM_12, UI_TEXT_COLOR);
					break;
				default:
					break;
			}
			break;
		case 8:
			if (view->menu_mode == APP_MENU_EDIT) {
				result = WritePanelLine(128, item->parameter->unit, FONT_INTER_MEDIUM_12, UI_ACCENT_COLOR);
			}
			break;
		case 9:
			if (view->menu_mode == APP_MENU_EDIT) {
				snprintf(settings.text, sizeof(settings.text), "%ld - %ld %s  |  Step %ld %s",
					(long)item->parameter->minimum, (long)item->parameter->maximum, item->parameter->unit,
					(long)item->parameter->step, item->parameter->unit);
				result = WritePanelLine(151, settings.text, FONT_INTER_MEDIUM_10, UI_MUTED_COLOR);
			} else if (closed) {
				result = WritePanelLine(151, "Hold OK to return Home", FONT_INTER_MEDIUM_10, UI_MUTED_COLOR);
			}
			break;
		case 10:
			if (view->menu_mode == APP_MENU_CONFIRM) {
				result = ST7789_DrawRoundedRectangle(28, 145, 124, 30, 5,
					view->confirm_ok ? UI_BORDER_COLOR : UI_ACCENT_COLOR,
					view->confirm_ok ? UI_CARD_BACKGROUND : UI_SELECTION_COLOR, UI_CARD_BACKGROUND);
			}
			break;
		case 11:
			if (view->menu_mode == APP_MENU_CONFIRM) {
				result = ST7789_WriteTextField(36, 152, 108, "CANCEL", FONT_INTER_MEDIUM_12,
					ST7789_TEXT_CENTER, view->confirm_ok ? UI_MUTED_COLOR : UI_TEXT_COLOR,
					view->confirm_ok ? UI_CARD_BACKGROUND : UI_SELECTION_COLOR);
			}
			break;
		case 12:
			if (view->menu_mode == APP_MENU_CONFIRM) {
				result = ST7789_DrawRoundedRectangle(168, 145, 124, 30, 5,
					view->confirm_ok ? UI_ACCENT_COLOR : UI_BORDER_COLOR,
					view->confirm_ok ? UI_SELECTION_COLOR : UI_CARD_BACKGROUND, UI_CARD_BACKGROUND);
			}
			break;
		case 13:
			if (view->menu_mode == APP_MENU_CONFIRM) {
				result = ST7789_WriteTextField(176, 152, 108, "OK", FONT_INTER_MEDIUM_12,
					ST7789_TEXT_CENTER, view->confirm_ok ? UI_TEXT_COLOR : UI_MUTED_COLOR,
					view->confirm_ok ? UI_SELECTION_COLOR : UI_CARD_BACKGROUND);
			}
			break;
		case 14:
			result = ST7789_DrawFilledRectangle(12, 201, 296, 1, UI_BORDER_COLOR);
			break;
		case 15: {
			const char *help = "UP/DOWN: Select     OK: Open";
			if (closed) help = "UP/DOWN: Page     OK: Open";
			if (view->menu_mode == APP_MENU_EDIT) help = "UP: Increase   DOWN: Decrease   OK: Save";
			if (view->menu_mode == APP_MENU_CONFIRM) help = "UP/DOWN: Choose     OK: Confirm";
			result = ST7789_WriteTextField(12, 207, 296, help, FONT_INTER_MEDIUM_10,
				ST7789_TEXT_LEFT, UI_TEXT_COLOR, UI_BACKGROUND);
			break;
		}
		case 16: {
			const char *help = "Hold OK: Back";
			if (closed) help = "Hold OK: Home";
			if (view->menu_mode == APP_MENU_EDIT || view->menu_mode == APP_MENU_CONFIRM) {
				help = "Hold OK: Cancel";
			}
			result = ST7789_WriteTextField(12, 223, 296, help, FONT_INTER_MEDIUM_10,
				ST7789_TEXT_LEFT, UI_MUTED_COLOR, UI_BACKGROUND);
			break;
		}
		default:
			settings.drawn_view = *view;
			settings.first_frame = false;
			settings.step = 0;
			return true;
	}

	if (result == ST7789_OK) settings.step++;
	return false;
}
