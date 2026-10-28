#include "App.h"
#include "../BUTTON/button.h"
#include "main.h"
#include <stddef.h>

static App_View app_view;



// =======================================================================
// Define all PARAMETERS of the App
// =======================================================================
static const App_Parameter parameter_refresh = {
	.value		= &app_view.UI_refresh_period_ms,
	.minimum	= APP_REFRESH_MIN_MS,
	.maximum	= APP_REFRESH_MAX_MS,
	.step		= APP_REFRESH_STEP_MS,
	.unit		= "ms"
};

static const App_Parameter parameter_developer_mode = {
	.value		= &app_view.developer_mode,
	.minimum	= 0,
	.maximum	= 1,
	.step		= 1,
	.unit		= ""
};

// =======================================================================
// Define the whole MENU of the settings of the App
// =======================================================================
static const App_Menu menu_setting_topLevel;
static const App_Menu menu_display;
static const App_Menu menu_calibration;


static const App_MenuItem settings_items[] = {
	{
		.type = APP_ITEM_SUBMENU,
		.submenu = &menu_display
	},
	{
		.type = APP_ITEM_SUBMENU,
		.submenu = &menu_calibration
	},
	{
		.label = "Developer Mode",
		.type = APP_ITEM_PARAMETER,
		.parameter = &parameter_developer_mode
	}
};

static const App_MenuItem display_items[] = {
	{
		.label = "Refresh period",
		.type = APP_ITEM_PARAMETER,
		.parameter = &parameter_refresh
	}
};

static const App_MenuItem calibration_items[] = {
	{
		.label = "Steering Wheel",
		.type = APP_ITEM_ACTION
	},
	{
		.label = "Road Side",
		.type = APP_ITEM_ACTION
	}
};

static const App_Menu menu_setting_topLevel = {
	"Settings",
	NULL,
	settings_items,
	sizeof(settings_items) / sizeof(settings_items[0])
};

static const App_Menu menu_display = {
	"Display",
	&menu_setting_topLevel,
	display_items,
	sizeof(display_items) / sizeof(display_items[0])
};

static const App_Menu menu_calibration = {
	"Calibration",
	&menu_setting_topLevel,
	calibration_items,
	sizeof(calibration_items) / sizeof(calibration_items[0])
};


// =======================================================================
// Private handlers
// =======================================================================

// Private handlers prototypes
static void App_MenuBack(void);
static void App_HandleNavigationButton(button_event_t event);
static void App_HandleSettingsButton(button_event_t event);

// Apply a BACK to the Menu, move to the higher level menu page!
static void App_MenuBack(void) {
	// Check that a parent menu page is available, and if not, just exit the Menu Navigation!
	if (app_view.menu->parent == NULL) {
		app_view.menu_mode = APP_MENU_CLOSED;
		return;
	}

	const App_Menu* child = app_view.menu;
	app_view.menu = child->parent;	// Move to the parent of current menu page
	
	// Find in the parent menu, the item I was previosuly in, so I can start from there the exploration of the parent menu!
	const App_Menu* parent = app_view.menu;
	for (uint8_t i = 0; i < parent->item_count; i++) {
		if (parent->items[i].type == APP_ITEM_SUBMENU && parent->items[i].submenu == child) {
			app_view.selected_item = i;
			break;
		}
	}
}


static void App_HandleNavigationButton(button_event_t event) {	
	// Long press of OK Button (if not inside settings), returns to home
	if (event.buttonID == BUTTON_OK && event.type == BUTTON_LONG_PRESS) {
		app_view.page = APP_PAGE_HOME;
		return;
	}

	// Any other long press in Page Navigation is ignored
	if (event.type != BUTTON_SHORT_PRESS) return;

	// In Page Navigation, Button Down and Button up are used to move though
	// the pages in opposite directions
	if (event.buttonID == BUTTON_DOWN) {
		// BUTTON DOWN short press --> Show next page
		if (app_view.page == APP_PAGE_COUNT - 1) {
			app_view.page = APP_PAGE_HOME;
		} else {
			app_view.page++;
		}
	} else if (event.buttonID == BUTTON_UP) {
		// BUTTON DOWN short press --> Show previous page
		if (app_view.page == APP_PAGE_HOME) {
			app_view.page = APP_PAGE_COUNT - 1;
		} else {
			app_view.page--;
		}
	}
}

static void App_HandleSettingsButton(button_event_t event) {
	// On the Settings landing page, OK button (short press) opens the menu, IF the menu was not already open
	// Any other button is used as usual to navigate between pages
	if (app_view.menu_mode == APP_MENU_CLOSED) {
		if ((event.buttonID == BUTTON_OK) && (event.type == BUTTON_SHORT_PRESS)) {
			app_view.menu = &menu_setting_topLevel;	// Select the Top Level menu as the one showed first
			app_view.selected_item = 0;				// Define the index of the item selected in the current menu
			app_view.menu_mode = APP_MENU_LIST;		// The menu, at its startup, must be navigable at its top level
		} else {
			// If the Menu is not open, other buttons are used as usual to navigate between pages
			App_HandleNavigationButton(event);
		}
		return;
	}
	
	// If the Menu Navigation is open, an OK long press has the effect of a BACK in the menu!
	const App_Menu*		menu = app_view.menu;
	const App_MenuItem*	item = &menu->items[app_view.selected_item];
	if ((event.buttonID == BUTTON_OK) && (event.type == BUTTON_LONG_PRESS)) {
		if (app_view.menu_mode == APP_MENU_LIST) {
			// Move to the previous Menu level!
			App_MenuBack();
		} else {
			// If the Menu is not in List mode (i'm scrolling through items)
			// move to the menu mode
			app_view.menu_mode = APP_MENU_LIST;
		}
		return;
	}

	// Only short presses of buttons are used to navigate menu!
	if (event.type != BUTTON_SHORT_PRESS) return;

	// Decide how to handle button inputs based on the Menu mode the App is in at the moment
	switch (app_view.menu_mode) {

		case APP_MENU_LIST:
			// Button Down moves the menu selection to next item (at last element it does nothing)
			if ((event.buttonID == BUTTON_DOWN) && (app_view.selected_item + 1 < menu->item_count)) {
				app_view.selected_item++;
			// Button Down moves the menu selection to previous item (at first element it does nothing)
			} else if ((event.buttonID == BUTTON_UP) && (app_view.selected_item != 0)) {
				app_view.selected_item--;
			// OK Button enters in the selected item
			} else if (event.buttonID == BUTTON_OK) {
				switch (item->type) {
					case APP_ITEM_SUBMENU:
						app_view.menu = item->submenu;	// The menu is now the selected submenu
						app_view.selected_item = 0;		// Start from the first item in this submenu
						break;

					case APP_ITEM_PARAMETER:
						app_view.edit_value = *item->parameter->value;	// Show the current value of the selected parameter to be modified!
						app_view.menu_mode = APP_MENU_EDIT;				// Set the Menu in Edit mode, so it is possible to edit the value of the parameter
						break;
					
					case APP_ITEM_ACTION:
						if (item->action == NULL) break;
						app_view.confirm_ok = false;					// By default, select the CANCEL option of the action
						app_view.menu_mode = APP_MENU_CONFIRM;			// Enter in the confirmation mode of the menu
						break;
				}
			}
			break;

		case APP_MENU_EDIT: {
			const App_Parameter *parameter = item->parameter;
			// OK button confirms the selected parameter value, and saves it in App
			if (event.buttonID == BUTTON_OK) {
				*item->parameter->value = app_view.edit_value;	// Saves the selected value in the App
				app_view.menu_mode = APP_MENU_LIST;				// Show the previous menu again
			
			} else if (event.buttonID == BUTTON_UP) {
				// Increment the selected parameter by the selected step value
				if (app_view.edit_value <= parameter->maximum - parameter->step) {
					app_view.edit_value += parameter->step;
				}
			
			} else if (event.buttonID == BUTTON_DOWN) {
				// Decrement the selected parameter by the selected step value
				if (app_view.edit_value >= parameter->minimum + parameter->step) {
					app_view.edit_value -= parameter->step;
				}
			}
			break;
		}

		case APP_MENU_CONFIRM:
			if ((event.buttonID == BUTTON_UP) || (event.buttonID == BUTTON_DOWN)) {
				app_view.confirm_ok = !app_view.confirm_ok;
			// Button OK press indicates the confirmation of the selectd action (OK or CANCEL)
			} else if (event.buttonID == BUTTON_OK) {
				if (app_view.confirm_ok) {
					item->action();						// If action is confirmed, launch the function!
				} else {
					app_view.menu_mode = APP_MENU_LIST;	// If the action is cacelled, show the menu again
				}
			}
			break;

		default:
			Error_Handler();
			break;
	}
}




// =======================================================================
// Public API
// =======================================================================

void App_Init(void) {
	// Put all the data in the main App State data structure at 0
	app_view = (App_View){0};

	// Explicity set all the fields that must not be zero at startup
	app_view.sensor.stale			= true;
	app_view.road.stale				= true;
	app_view.drive_mode				= APP_DRIVE_NORMAL;
	app_view.page					= APP_PAGE_HOME;
	app_view.menu					= &menu_setting_topLevel;
	app_view.menu_mode				= APP_MENU_CLOSED;
	app_view.UI_refresh_period_ms	= APP_REFRESH_DEFAULT_MS;
	app_view.developer_mode			= APP_DEVELOPER_MODE_DEFAULT;

	// Initialize all modules directly controlled by the App!
	BUTTON_init();
}

void App_Process(void) {	
	Sensor_TakeUpdate		(&app_view.sensor);
	Road_TakeUpdate			(&app_view.road);
	Operating_TakeUpdate	(&app_view.operating);
	
	// Handle all Button Events
	button_event_t event;
	while (button_getEvent(&event)) {
		// Handle the Mode Button Short Press (always changes the Drive Mode 
		// to the next one)
		if (event.buttonID == BUTTON_MODE) {
			if (event.type == BUTTON_SHORT_PRESS) {
				app_view.drive_mode++;
				if (app_view.drive_mode == APP_DRIVE_COUNT) {
					app_view.drive_mode = APP_DRIVE_NORMAL;
				}
			}
			continue;
		}
		if (app_view.page == APP_PAGE_SETTINGS) {
			App_HandleSettingsButton(event);
		} else {
			App_HandleNavigationButton(event);
		}
	}
}

void App_GetView(App_View *view) {
	if (view == NULL) {
		Error_Handler();
		return;
	}
	*view = app_view;
}
