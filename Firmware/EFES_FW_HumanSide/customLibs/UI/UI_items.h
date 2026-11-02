#ifndef UI_ITEMS_H
#define UI_ITEMS_H

#include "App.h"
#include "st7789.h"
#include <stdint.h>

// =======================================================================
// Shared components
// =======================================================================

uint16_t UI_SensorDeviation(const Sensor_State *state);


// =======================================================================
// Header
// =======================================================================

// General Dimensions
#define HEADER_HEIGHT			22
#define HEADER_BORDER_HEIGHT	1		// Height of the line that ends the header at the bottom!
#define HEADER_BACKGROUND_COLOR	UI_BAR_BACKGROUND	// Background color of the Header rectangle

#define HEADER_BORDER_COLOR	UI_BORDER_COLOR

// Header Title Parameters
#define HEADER_TITLE_X		8		// Horizontal position of the header title
#define HEADER_FONT			FONT_BARLOW_SEMI_CONDENSED_BOLD_14	// 
#define HEADER_TEXT_COLOR	UI_TEXT_COLOR

// Header Dots parameters
#define HEADER_DOT_ACTIVE_RADIUS	4		// Dimension of the Active Dot
#define HEADER_DOT_RADIUS			2		// Dimension of the Inactive dots
#define HEADER_DOT_SPACING			10		// Distance between dot centers (pixels)
#define HEADER_DOT_RIGHT_MARGIN		10		// Distance from the right edge to the last dot center
#define HEADER_DOT_ACTIVE_COLOR		UI_TITLE_COLOR
#define HEADER_DOT_INACTIVE_COLOR	UI_INACTIVE_COLOR

// Runtime state of the header
typedef struct {
	bool		drawn;
	char		title[32];
	App_Page	page;
	uint8_t		count;
	uint8_t		step;
	uint8_t		dot;
} UI_Header;

void UI_Header_startRendering(UI_Header *header, App_Page page, const char *title);
bool UI_Header_render(UI_Header *header);



// =======================================================================
// Driving mode
// =======================================================================

// General Dimensions
#define DRIVING_MODE_X				3
#define DRIVING_MODE_Y				205
#define DRIVING_MODE_HEIGHT			31
#define DRIVING_MODE_CORNER_RADIUS	5

// Driving mode icon and text parameters
#define DRIVING_MODE_ICON_TEXT_GAP	17		// Distance between Icon and the Text in the Driving Mode item

// Separator parameters
#define DRIVING_MODE_SEPARATOR_WIDTH			2
#define DRIVING_MODE_SEPARATOR_VERTICAL_MARGIN	5

// Font and colors
#define DRIVING_MODE_FONT				FONT_RAJDHANI_BOLD_28
#define DRIVING_MODE_TEXT_COLOR			UI_TEXT_COLOR
#define DRIVING_MODE_SEPARATOR_COLOR	UI_TEXT_COLOR
#define DRIVING_MODE_BACKGROUND_COLOR	UI_BACKGROUND
#define DRIVING_MODE_COMFORT_COLOR		UI_DRIVING_MODE_COMFORT_COLOR
#define DRIVING_MODE_ECO_COLOR			UI_DRIVING_MODE_ECO_COLOR
#define DRIVING_MODE_SPORT_COLOR		UI_DRIVING_MODE_SPORT_COLOR

// Runtime state of the drive mode
typedef struct {
	bool			drawn;
	App_DriveMode	driving_mode;
	uint8_t			step;
	uint16_t		symbol_x;
	uint16_t		text_x;
} UI_DrivingMode;

void UI_DrivingMode_startRendering(UI_DrivingMode *driving_mode, App_DriveMode driving_mode_value);
bool UI_DrivingMode_render(UI_DrivingMode *driving_mode);



// =======================================================================
// Developer mode rendering time
// =======================================================================

// Field position and dimensions
#define DEVELOPER_MODE_X		132
#define DEVELOPER_MODE_WIDTH	96
#define DEVELOPER_MODE_TEXT_GAP	4

// Font and colors
#define DEVELOPER_MODE_FONT				FONT_BARLOW_SEMI_CONDENSED_BOLD_10
#define DEVELOPER_MODE_TEXT_COLOR		UI_MUTED_COLOR
#define DEVELOPER_MODE_BACKGROUND_COLOR	HEADER_BACKGROUND_COLOR

// Runtime state of the developer rendering time
typedef struct {
	bool		drawn;
	uint8_t		step;
	uint32_t	elapsed_ms;
	uint32_t	drawn_elapsed_ms;
	uint16_t	label_width;
	uint16_t	unit_width;
} UI_DeveloperMode;

// First draw writes labels and value; subsequent requests update only the value.
void UI_DeveloperMode_startRendering(UI_DeveloperMode *developer_mode, uint32_t elapsed_ms, bool first_draw);
bool UI_DeveloperMode_render(UI_DeveloperMode *developer_mode);



// =======================================================================
// Graph
// =======================================================================

// Automatic Y scale
#define GRAPH_SCALE_MARGIN_PERCENT	20
#define GRAPH_SCALE_SHRINK_PERCENT	70
#define GRAPH_SCALE_SHRINK_DELAY_MS	3000

#define GRAPH_MAX_SERIES			4
#define GRAPH_MAX_SAMPLES			264
#define GRAPH_AXIS_FONT				FONT_INTER_MEDIUM_10
#define GRAPH_LEGEND_FONT			FONT_BARLOW_SEMI_CONDENSED_BOLD_10
#define GRAPH_AXIS_LEFT_MARGIN		6
#define GRAPH_AXIS_GAP				4
#define GRAPH_TIME_LABEL_WIDTH		40
#define GRAPH_TIME_LABEL_GAP		1
#define GRAPH_LEGEND_GAP			0
#define GRAPH_LEGEND_LINE_WIDTH		13
#define GRAPH_LEGEND_LINE_HEIGHT	2
#define GRAPH_LEGEND_TEXT_GAP		5
#define GRAPH_LEGEND_SERIES_GAP		20



// Customization of one signal; instances are defined by the page.
typedef struct {
	uint16_t	color;
	const char*	legend;
} UI_GraphSeriesConfig;

// Appearance and data window selected by the page
typedef struct {
	uint16_t					x, y;				// Position of the Top Left corner of the Graph Item
	int16_t						width, height;		// Dimension of the Graph item
	uint16_t					color_grid;			// Color of the internal grid of the Graph 
	uint16_t					color_background;	// Color of the graph background
	const UI_GraphSeriesConfig*	series;				// Characteristics of the Data Series to be shown in the graph
	uint8_t						series_count;		// Number of series to show in the graph
	uint16_t					capacity;			// Max number of samples in the buffer
	uint32_t					history_ms;			// Total time rapresented by the Graph (basically the scale of X axis)
	uint16_t					text_color;			// Color of all the text in the Graph
	uint8_t						max_digits;			// Maximum numeric digits, excluding sign and decimal point
	uint8_t						max_decimal_places;	// Maximum Y-axis decimal places
	bool						symmetric_scale;	// Is the Y axis symmetric?
	uint16_t					minimum_scale;		// Minimum range for Y axis
} UI_GraphConfig;

// Runtime state of the history buffer
typedef struct {
	int16_t	values[GRAPH_MAX_SERIES];
} UI_GraphSample;

typedef struct {
	UI_GraphSample	samples[GRAPH_MAX_SAMPLES];		// Buffer of samples (1 sample for each instant for each data series)
	uint16_t		count;							// Number of valid samples currently in Buffer
	uint16_t		write;							// Index of the next position to write
	uint32_t		last_tick;						// Last handled sample time
	uint32_t		version;						// 
} UI_Trace;

// Runtime state and storage belong to the graph item.
typedef struct {
	UI_GraphConfig	config;				// General configuration of the Graph
	uint32_t		sample_period_ms;	// Period between two consecutive samples (computed from the config. informations)
	UI_Trace		history;			// Data series

	UI_GraphSample	snapshot[GRAPH_MAX_SAMPLES];	// 
	uint16_t		legend_x[GRAPH_MAX_SERIES];		// 
	uint16_t		legend_y[GRAPH_MAX_SERIES];		// 
	uint16_t		snapshot_count;
	uint32_t		snapshot_version;
	uint32_t		drawn_version;
	uint32_t		shrink_started_at_ms;
	bool			shrink_pending;
	int16_t			minimum;	
	int16_t			maximum;
	int16_t			drawn_minimum;
	int16_t			drawn_maximum;
	uint8_t			decimal_places;					// Common format selected for the current Y scale
	bool			drawn;
	bool			first_draw;
	uint8_t			step;
	uint8_t			tick;
} UI_Graph;

// Init once; process keeps sampling even when the page is not visible.
void UI_Graph_init				(UI_Graph *graph, const UI_GraphConfig *config);
void UI_Graph_process			(UI_Graph *graph, UI_GraphSample sample, bool usable, uint32_t now);
void UI_Graph_startRendering	(UI_Graph *graph, bool first_draw);	// Capture a stable snapshot; redraw axes only on first_draw or a scale change.
bool UI_Graph_render			(UI_Graph *graph);

#endif
