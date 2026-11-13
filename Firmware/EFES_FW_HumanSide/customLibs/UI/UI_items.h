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
#define HEADER_DOT_SPACING			10		// Distance between dot centers
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
// Segmented bar
// =======================================================================

#define SEGMENTED_BAR_MAX_DECIMAL_PLACES	3

// Appearance and numeric range selected by the page; zero is at the center.
typedef struct {
	uint16_t	x, y;				// Top-left corner of the entire item, including labels
	uint16_t	width, height;		// Total dimensions of the item, including labels
	uint16_t	segment_gap;		// Space between consecutive segments
	uint8_t		segments_per_side;	// Number of segments on each side of zero
	uint16_t	center_gap;			// Space between the zero marker and the nearest segment
	uint16_t	zero_width;			// Width of the zero marker
	uint16_t	zero_extension;		// Extension above and below the segments
	int16_t		full_scale;			// Absolute value represented by a completely filled side
	uint16_t	value_divisor;		// Input units per displayed unit (10 for values supplied in tenths)
	uint8_t		decimal_places;		// Fixed number of decimal places, up to SEGMENTED_BAR_MAX_DECIMAL_PLACES
	const char*	unit;				// Suffix appended to every label; empty string for no unit
	FontId		label_font;			// Font used for the numeric labels
	uint16_t	label_min_gap;		// Minimum horizontal space between the edges of consecutive labels
	uint16_t	label_gap;			// Vertical space between the zero marker and labels
	uint16_t	color_fill;			// Color of the filled portion of the segments
	uint16_t	color_track;		// Color of the empty portion of the segments
	uint16_t	color_zero;			// Color of the zero marker
	uint16_t	color_label;		// Color of the numeric labels
	uint16_t	color_background;	// Background color behind the labels
} UI_SegmentedBarConfig;

// Runtime state of the segmented bar
typedef struct {
	const UI_SegmentedBarConfig*	config;			// Configuration owned by the page; must remain available while the item is used
	uint16_t						center_x;		// Left edge of the zero marker, computed from the total width
	uint16_t						segment_height;	// Segment height remaining after reserving labels and zero extensions
	uint16_t						fill_width[2];	// Total fillable pixels on each side, excluding gaps
	uint16_t						label_step;		// Numeric interval between intermediate labels, in input units
	uint16_t						label_count;	// Number of labels that fit with the requested minimum gap
	int16_t							value;			// Stable value captured for the current rendering, limited to the configured range
	int16_t							drawn_value;	// Value used in the previous completed rendering, to update only changed portions
	bool							drawn;			// Is the requested rendering complete?
	uint8_t							step;			// Current rendering phase (tracks, zero marker, labels or fill update)
	uint16_t						segment;		// Index of the next segment to process, from left to right
	uint16_t						label;			// Index of the next label to render
} UI_SegmentedBar;

void UI_SegmentedBar_init(UI_SegmentedBar *bar, const UI_SegmentedBarConfig *config);
void UI_SegmentedBar_startRendering(UI_SegmentedBar *bar, int32_t value, bool first_draw);
bool UI_SegmentedBar_render(UI_SegmentedBar *bar);



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



// Customization of one Graph Signal
typedef struct {
	uint16_t	color;
	const char*	legend;
} UI_GraphSeriesConfig;

// General configuration of the UI Graph Item
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
	uint32_t		version;						// Counter incremeneted at each new sample (so I know when the data changes)
} UI_Trace;

// Runtime state and storage belong to the graph item.
typedef struct {
	// UI Graph Item configuration (and parameters directly computed from Config.)
	UI_GraphConfig	config;						// General configuration of the Graph
	uint32_t		sample_period_ms;			// Period between two consecutive samples (computed from the config. informations)
	uint16_t		legend_x[GRAPH_MAX_SERIES];	// Position of the data series Legends
	uint16_t		legend_y[GRAPH_MAX_SERIES];	// Position of the data series Legends 
	
	// Main Data series of the Graph
	UI_Trace		history;

	// Snapshot of all the Data Series to be rendered (I need this save, because data can change while I render)
	UI_GraphSample	snapshot[GRAPH_MAX_SAMPLES];	
	uint16_t		snapshot_count;				//	
	uint32_t		snapshot_version;			//		

	// Run Time parameters of the UI Graph
	uint32_t		drawn_version;				// Version of Data Series that is drawn in the graph				
	uint32_t		shrink_started_at_ms;		// Timestamp of when the axis shrink started
	bool			shrink_pending;				// If = 1, idicates that an axis shirk is needed (and so I check the timestamp to execute that after delay)
	int16_t			maximum;					// Y-Axis limit to be used in the current rendering
	int16_t			drawn_maximum;				// Y-Axis limit used in the previous rendering (so if the current one are the same, some rendering can be optimized)
	uint8_t			decimal_places;				// Common format selected for the current Y scale
	bool			drawn;						// Is the rendering complete?
	bool			first_draw;					// Is this the first Grph rendering?
	uint8_t			step;						// Main rendering step
	uint8_t			tick;						// Phase inside the rendering step
} UI_Graph;

void UI_Graph_init				(UI_Graph *graph, const UI_GraphConfig *config);
void UI_Graph_updateHistory		(UI_Graph *graph, UI_GraphSample sample, bool usable, uint32_t now);
void UI_Graph_startRendering	(UI_Graph *graph, bool first_draw);	
bool UI_Graph_render			(UI_Graph *graph);

#endif
