#ifndef APP_H
#define APP_H

#include <stdbool.h>
#include <stdint.h>
#include "../Communication/Communication.h"

// ==============================================================================
// Steer By Wire Application parameter that can be personalizable
// ==============================================================================

// Display Referesh Rate parameter (settable in the UI setting menu)
#define APP_REFRESH_DEFAULT_MS	20
#define APP_REFRESH_MIN_MS		5
#define APP_REFRESH_MAX_MS		1000
#define APP_REFRESH_STEP_MS		5

#define APP_DEVELOPER_MODE_DEFAULT	1


// ==============================================================================
// Steer By Wire Application data structures
// ==============================================================================

// Available driving Modes implemeted by the App
typedef enum {
	APP_DRIVE_NORMAL,
	APP_DRIVE_ECO,
	APP_DRIVE_SPORT,
	APP_DRIVE_COUNT
} App_DriveMode;

// Pages avaiable in the Steer by Wire UI
typedef enum {
	APP_PAGE_HOME,
	APP_PAGE_SENSOR,
	APP_PAGE_STEERING,
	APP_PAGE_SETTINGS,
	APP_PAGE_COUNT
} App_Page;


// Possible items in the a UI Menu!
typedef enum {
	APP_ITEM_SUBMENU,
	APP_ITEM_PARAMETER,
	APP_ITEM_ACTION
} App_MenuItemType;

// Enum that defines all possibile modes in which the menu can be
// Basically it defines how the User can interact with the menu 
typedef enum {	
	APP_MENU_CLOSED,	// Menu navigation not yet opened
	APP_MENU_LIST,		// Navigate the items of the current menu
	APP_MENU_EDIT,		// Edit a parameter value
	APP_MENU_CONFIRM	// Choose OK or CANCEL before executing an action
} App_MenuMode;




// Type that generalize a parameter of the "Steer by Wire" App, which can be 
// modified with via the Settings menu in UI
typedef struct {
	int32_t*	value;		// Current value of the Parameter
	int32_t		minimum;	// Max value usable for parameter
	int32_t		maximum;	// Min value usable for parameter
	int32_t		step;		// Step usable to modify the parameter
	const char*	unit;		// Label that defines the unit of measure of the Parameter
} App_Parameter;

// Type that defines a pointer to a function
typedef void (*App_Action)(void);	
typedef struct App_Menu App_Menu;

typedef struct {
	const char*				label;		// Title of the current Menu Item 
	App_MenuItemType		type;		// Type of the Item (so the item can be handled in different ways)
	const App_Menu*			submenu;	// Pointer to submenu (if this item is a SUBMENU)
	const App_Parameter*	parameter;	// Parameter to edit (if this item is a PARAMETER)
	App_Action				action;		// Action/Function to execute (if this item is a ACTION)
} App_MenuItem;

struct App_Menu {
	const char*			title;			// Title of the current Menu
	const App_Menu*		parent;			// Parent Menu of the current Sub-Menu (used when I need to navigate BACK in menu)
	const App_MenuItem*	items;			// List of items in the menu
	uint8_t				item_count;		// Number of sub items in the menu
};


// App general state data structure
typedef struct {
	// UI State
	App_Page			page;					// Current page of the UI being shown
	const App_Menu*		menu;					// Current menu shown in the UI (if in Settings page)
	App_MenuMode		menu_mode;				// Current menu mode, deciding how User can interact with menu
	uint8_t				selected_item;			// Current menu item selected (basically the row of the menu selected)
	int32_t				edit_value;				// Value under editing in Menu Editing Mode
	bool				confirm_ok;				// OK or CANCEL selector in Menu Selection Mode
	int32_t				UI_refresh_period_ms;	// UI refersh rate
	int32_t				developer_mode;			// 0: disabled, 1: active

	// Device state exposed to readers
	Sensor_State		sensor;
	RoadFeedback_State	road;
	Operating_State		operating;
	App_DriveMode		drive_mode; /* App-owned: selected by MODE. */

} App_View;



void App_Init		(void);				// General Initialization of the SteerByWire Application
void App_Process	(void);				// Function to call in the main SuperLoop to advance the App tasks
void App_GetView	(App_View *view);


#endif
