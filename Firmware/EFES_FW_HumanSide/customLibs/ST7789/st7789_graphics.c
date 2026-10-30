#include "st7789_graphics.h"
#include "st7789_transport.h"
/* Short critical sections protect publication of buffers and DMA launches.
 * Preserve PRIMASK: these helpers are also used from callbacks.
 */
#include "main.h"
#include <math.h>
#include <stdbool.h>

typedef enum { FREE, FILLING, READY, IN_FLIGHT } BufferState;
typedef enum { SOLID, IMAGE_BYTES, TEXT_PIXELS, HORIZONTAL_GRADIENT, WHEEL_PIXELS, ROUNDED_PIXELS, PROGRESS_PIXELS, GRAPH_PIXELS, CIRCLE_PIXELS, ASSET_PIXELS } PixelSource;
typedef enum { FILL, LINE, RECTANGLE, CIRCLE, FILLED_CIRCLE,
               TRIANGLE, FILLED_TRIANGLE, IMAGE, TEXT, GRADIENT, WHEEL, ROUNDED_RECTANGLE, PROGRESS_BAR, GRAPH, INDEXED_ASSET } JobKind;

typedef struct {
    uint8_t data[ST7789_BUFFER_PIXELS * 2U];
    uint16_t pixels;
    volatile BufferState state;
} PixelBuffer;

typedef struct {
    int32_t x, y, end, dx, dy, error, y_step;
    uint8_t steep;
} LineCursor;

typedef struct {
    JobKind kind;
    uint16_t color, background;
    int32_t x[3], y[3], radius, row;
    uint8_t stage;
    LineCursor line;
    const uint8_t *image;
    const GraphicAsset *asset;
    const ST7789_Graph *graph;
    const ST7789_GraphSample *graph_samples;
    uint16_t graph_count;
    uint8_t asset_tinted;
    const char *text;
	char text_buffer[ST7789_TEXT_BUFFER_SIZE];
    const FontInfo *font;
    uint16_t text_palette[16];
    int32_t text_x, text_y, text_offset;
    const char *line_start, *line_end;
    uint16_t field_width;
    uint16_t number_cell; /* Zero for proportional text. */
    ST7789_TextAlign text_align;
    int32_t cosine, sine;
    uint16_t accent;
} DrawingJob;

typedef struct {
    uint16_t x0, y0, x1, y1;
    PixelSource source;
} Window;

static PixelBuffer buffers[2];
static DrawingJob job;
static Window window;
static volatile ST7789_State drawing_state = ST7789_STATE_ERROR;
static volatile int8_t active_buffer = -1;
static volatile uint8_t window_active;
static uint8_t initialized, prepare_index, send_index;
static uint32_t remaining_pixels, total_pixels, completed_pixels, source_offset;

static int32_t Min(int32_t a, int32_t b) { return a < b ? a : b; }
static int32_t Max(int32_t a, int32_t b) { return a > b ? a : b; }
static int32_t Abs(int32_t x) { return x < 0 ? -x : x; }

ST7789_State ST7789_GetState(void) { return drawing_state; }
HAL_StatusTypeDef ST7789_GetError(void) { return ST7789_TransportGetError(); }

ST7789_Result ST7789_GraphicsReady(void)
{
    if (drawing_state == ST7789_STATE_BUSY) return ST7789_BUSY;
    return drawing_state == ST7789_STATE_IDLE ? ST7789_OK : ST7789_ERROR;
}

void ST7789_GraphicsReset(uint8_t ready)
{
    initialized = ready;
    active_buffer = -1;
    window_active = 0;
    buffers[0].state = buffers[1].state = FREE;
    drawing_state = ready ? ST7789_STATE_IDLE : ST7789_STATE_ERROR;
}

void ST7789_GraphicsError(void)
{
    active_buffer = -1;
    window_active = 0;
    buffers[0].state = buffers[1].state = FREE;
    ST7789_TransportEndPixels();
    drawing_state = ST7789_STATE_ERROR;
}

ST7789_Result ST7789_ClearError(void)
{
    if (drawing_state == ST7789_STATE_BUSY) return ST7789_BUSY;
    if (!initialized || ST7789_TransportClearError() != HAL_OK) return ST7789_ERROR;
    ST7789_GraphicsReset(1);
    return ST7789_OK;
}

static uint8_t OnScreen(uint16_t x, uint16_t y)
{
    return x < ST7789_WIDTH && y < ST7789_HEIGHT;
}

static void NewJob(JobKind kind, uint16_t color)
{
    /* Main is the only producer; this is called only when IDLE. */
    job.kind = kind;
    job.number_cell = 0;
    job.asset_tinted = 0;
    job.color = color;
    job.stage = 0;
    window_active = 0;
    drawing_state = ST7789_STATE_BUSY;
}

/* Called only while IDLE, before accepting a text job. */
static bool CopyText(const char *text)
{
	if (text == NULL) return false;
	for (uint32_t i = 0; i < sizeof(job.text_buffer); i++) {
		job.text_buffer[i] = text[i];
		if (text[i] == '\0') return true;
	}
	return false;
}

/* Only 16 foreground/background blends per text request, not per pixel. */
static void PrepareTextPalette(void)
{
    for (uint32_t coverage = 0; coverage < 16; coverage++) {
        uint32_t background = 15U - coverage;
        uint32_t red = (((job.color >> 11) & 31U) * coverage +
                        ((job.background >> 11) & 31U) * background + 7U) / 15U;
        uint32_t green = (((job.color >> 5) & 63U) * coverage +
                          ((job.background >> 5) & 63U) * background + 7U) / 15U;
        uint32_t blue = ((job.color & 31U) * coverage +
                         (job.background & 31U) * background + 7U) / 15U;
        job.text_palette[coverage] = (uint16_t)((red << 11) | (green << 5) | blue);
    }
}

static void InitLine(int32_t x0, int32_t y0, int32_t x1, int32_t y1)
{
    LineCursor *line = &job.line;
    line->steep = Abs(y1 - y0) > Abs(x1 - x0);
    if (line->steep) {
        int32_t t = x0; x0 = y0; y0 = t;
        t = x1; x1 = y1; y1 = t;
    }
    if (x0 > x1) {
        int32_t t = x0; x0 = x1; x1 = t;
        t = y0; y0 = y1; y1 = t;
    }
    line->x = x0;
    line->y = y0;
    line->end = x1;
    line->dx = x1 - x0;
    line->dy = Abs(y1 - y0);
    line->error = line->dx / 2;
    line->y_step = y0 < y1 ? 1 : -1;
}

/* Windows are contiguous pixels only. Clipping never changes the background. */
static uint8_t SolidWindow(int32_t x0, int32_t y0, int32_t x1, int32_t y1)
{
    x0 = Max(x0, 0); y0 = Max(y0, 0);
    x1 = Min(x1, ST7789_WIDTH - 1); y1 = Min(y1, ST7789_HEIGHT - 1);
    if (x0 > x1 || y0 > y1) return 0;
    window.x0 = (uint16_t)x0; window.y0 = (uint16_t)y0;
    window.x1 = (uint16_t)x1; window.y1 = (uint16_t)y1;
    window.source = SOLID;
    return 1;
}

static uint8_t NextLineWindow(void)
{
    LineCursor *line = &job.line;
    if (line->x > line->end) return 0;
    int32_t start = line->x, minor = line->y;
    /* Merge the entire horizontal/vertical run from Bresenham. */
    do {
        line->x++;
        line->error -= line->dy;
        if (line->error < 0) {
            line->y += line->y_step;
            line->error += line->dx;
        }
    } while (line->x <= line->end && line->y == minor);
    return line->steep ? SolidWindow(minor, start, minor, line->x - 1) :
                         SolidWindow(start, minor, line->x - 1, minor);
}

static int32_t FloorDivide(int32_t numerator, int32_t denominator)
{
    int32_t q = numerator / denominator;
    return q - (numerator % denominator < 0);
}

static int32_t CeilDivide(int32_t numerator, int32_t denominator)
{
    return -FloorDivide(-numerator, denominator);
}

static int NextFilledTriangleWindow(void)
{
    int32_t last_y = Max(job.y[0], Max(job.y[1], job.y[2]));
    if (job.row > last_y) return 0;
    int32_t y = job.row++;
    int32_t low_n = 0, low_d = 1, high_n = 0, high_d = 1;
    uint8_t found = 0;
    for (uint8_t edge = 0; edge < 3; edge++) {
        uint8_t next = (edge + 1U) % 3U;
        int32_t xa = job.x[edge], ya = job.y[edge];
        int32_t xb = job.x[next], yb = job.y[next];
        if (ya > yb) {
            int32_t t = xa; xa = xb; xb = t;
            t = ya; ya = yb; yb = t;
        }
        if (y < ya || y > yb) continue;
        /* Horizontal edges contribute both endpoints on their own row. */
        uint8_t samples = ya == yb ? 2 : 1;
        for (uint8_t sample = 0; sample < samples; sample++) {
            int32_t d = ya == yb ? 1 : yb - ya;
            int32_t n = ya == yb ? (sample == 0 ? xa : xb) :
                        xa * d + (y - ya) * (xb - xa);
            if (!found || n * low_d < low_n * d) { low_n = n; low_d = d; }
            if (!found || n * high_d > high_n * d) { high_n = n; high_d = d; }
            found = 1;
        }
    }
    if (!found) return -1;
    return SolidWindow(CeilDivide(low_n, low_d), y,
                       FloorDivide(high_n, high_d), y) ? 1 : -1;
}

typedef struct {
    int32_t pen, left, right;
} TextLine;

static const FontGlyph *TextGlyph(const FontInfo *font, unsigned char ch)
{
    return &font->glyphs[ch - font->first_char];
}

static int32_t NumberAdvance(const FontInfo *font, unsigned char ch, uint16_t cell)
{
    if (ch != '.') return cell;
    const FontGlyph *glyph = TextGlyph(font, ch);
    return Max(glyph->advance, glyph->width);
}

static TextLine AppendGlyph(TextLine line, const FontGlyph *glyph)
{
    if (glyph->width != 0 && glyph->height != 0) {
        line.left = Min(line.left, line.pen + glyph->x_offset);
        line.right = Max(line.right, line.pen + glyph->x_offset + glyph->width);
    }
    line.pen += glyph->advance;
    line.right = Max(line.right, line.pen);
    return line;
}

static TextLine MeasureLine(const FontInfo *font, const char *start, const char *end)
{
    TextLine line = {0};
    for (const char *p = start; p != end; p++)
        line = AppendGlyph(line, TextGlyph(font, (unsigned char)*p));
    return line;
}

ST7789_Result ST7789_MeasureText(const char *text, FontId font, ST7789_TextSize *size)
{
    if (text == NULL || size == NULL || (unsigned)font >= FONT_COUNT)
        return ST7789_INVALID_ARGUMENT;
    const FontInfo *info = &Fonts[font];
    TextLine line = {0};
    size->width = 0;
    size->height = *text != '\0' ? info->height : 0;
    for (const char *p = text; *p != '\0'; p++) {
        unsigned char ch = (unsigned char)*p;
        if (ch == '\n') {
            size->width = Max(size->width, line.right - line.left);
            size->height += info->height;
            line = (TextLine){0};
        } else {
            if (ch < info->first_char || ch > info->last_char)
                return ST7789_INVALID_ARGUMENT;
            line = AppendGlyph(line, TextGlyph(info, ch));
        }
    }
    size->width = Max(size->width, line.right - line.left);
    return ST7789_OK;
}

static int NextTextWindow(void)
{
    const char *start = job.text;
    const char *end = start;
    TextLine line = {0};
    int32_t width;

    if (job.field_width != 0) {
        if (job.stage++) return 0;
        while (*end != '\0') end++;
        width = job.field_width;
        if (job.number_cell != 0) {
            int32_t number_width = 0;
            for (const char *p = start; p != end; p++)
                number_width += NumberAdvance(job.font, (unsigned char)*p, job.number_cell);
            job.text_offset = width - number_width;
        } else {
            line = MeasureLine(job.font, start, end);
            int32_t spare = width - (line.right - line.left);
            job.text_offset = -line.left;
            if (job.text_align == ST7789_TEXT_CENTER) job.text_offset += spare / 2;
            if (job.text_align == ST7789_TEXT_RIGHT) job.text_offset += spare;
        }
    } else {
        if (*start == '\0' || job.text_y + job.font->height > ST7789_HEIGHT) return 0;
        if (*start == '\n') {
            job.text++;
            job.text_x = 0;
            job.text_y += job.font->height;
            return -1;
        }
        while (*end != '\0' && *end != '\n') {
            TextLine next = AppendGlyph(line, TextGlyph(job.font, (unsigned char)*end));
            if (next.right - next.left > ST7789_WIDTH - job.text_x) break;
            line = next;
            end++;
        }
        if (end == start) {
            job.text_x = 0;
            job.text_y += job.font->height;
            return -1;
        }
        width = line.right - line.left;
        job.text_offset = -line.left;
    }

    job.line_start = start;
    job.line_end = end;
    window.x0 = job.text_x;
    window.y0 = job.text_y;
    job.text = *end == '\n' ? end + 1 : end;
    job.text_x = 0;
    job.text_y += job.font->height;
    if (width == 0) return -1;
    window.x1 = window.x0 + width - 1;
    window.y1 = window.y0 + job.font->height - 1;
    window.source = TEXT_PIXELS;
    return 1;
}

static int NextWindow(void)
{
    switch (job.kind) {
    case FILL:
    case IMAGE:
    case GRADIENT:
    case WHEEL:
    case ROUNDED_RECTANGLE:
    case PROGRESS_BAR:
    case GRAPH:
    case INDEXED_ASSET:
        if (job.stage++) return 0;
        SolidWindow(job.x[0], job.y[0], job.x[1], job.y[1]);
        if (job.kind == IMAGE) window.source = IMAGE_BYTES;
        if (job.kind == GRADIENT) window.source = HORIZONTAL_GRADIENT;
        if (job.kind == WHEEL) window.source = WHEEL_PIXELS;
        if (job.kind == ROUNDED_RECTANGLE) window.source = ROUNDED_PIXELS;
        if (job.kind == PROGRESS_BAR) window.source = PROGRESS_PIXELS;
        if (job.kind == GRAPH) window.source = GRAPH_PIXELS;
        if (job.kind == INDEXED_ASSET) window.source = ASSET_PIXELS;
        return 1;
    case LINE:
        return NextLineWindow();
    case RECTANGLE:
        /* Do not transmit corner pixels twice. Degenerate rectangles work. */
        while (job.stage < 4) {
            uint8_t edge = job.stage++;
            if (edge == 0)
                return SolidWindow(job.x[0], job.y[0], job.x[1], job.y[0]);
            if (edge == 1 && job.y[1] > job.y[0])
                return SolidWindow(job.x[0], job.y[1], job.x[1], job.y[1]);
            if (edge == 2 && job.y[1] - job.y[0] > 1)
                return SolidWindow(job.x[0], job.y[0] + 1, job.x[0], job.y[1] - 1);
            if (edge == 3 && job.x[1] > job.x[0] && job.y[1] - job.y[0] > 1)
                return SolidWindow(job.x[1], job.y[0] + 1, job.x[1], job.y[1] - 1);
        }
        return 0;
    case CIRCLE:
    case FILLED_CIRCLE:
        if (job.stage++) return 0;
        SolidWindow(job.x[0] - job.radius, job.y[0] - job.radius,
                    job.x[0] + job.radius, job.y[0] + job.radius);
        window.source = CIRCLE_PIXELS;
        return 1;
    case TRIANGLE:
        if (NextLineWindow()) return 1;
        if (++job.stage == 3) return 0;
        InitLine(job.x[job.stage], job.y[job.stage],
                 job.x[(job.stage + 1U) % 3U], job.y[(job.stage + 1U) % 3U]);
        return -1;
    case FILLED_TRIANGLE:
        return NextFilledTriangleWindow();
    case TEXT:
        return NextTextWindow();
    }
    return 0;
}

static uint16_t GradientColor(uint32_t position)
{
    uint32_t x = position % ST7789_WIDTH;
    uint32_t distance = x < ST7789_WIDTH - 1U - x ? x : ST7789_WIDTH - 1U - x;
    const uint32_t middle = (ST7789_WIDTH - 1U) / 2U;
    uint32_t edge_weight = middle - distance;
    /* Interpolate the RGB565 components independently, rounding to nearest.
     * Both outer columns are edge_color; both central columns are center_color.
     */
    uint32_t r = (((job.color >> 11) & 31U) * edge_weight +
                  ((job.background >> 11) & 31U) * distance + middle / 2U) / middle;
    uint32_t g = (((job.color >> 5) & 63U) * edge_weight +
                  ((job.background >> 5) & 63U) * distance + middle / 2U) / middle;
    uint32_t b = ((job.color & 31U) * edge_weight +
                  (job.background & 31U) * distance + middle / 2U) / middle;
    return (uint16_t)((r << 11) | (g << 5) | b);
}

static uint16_t WheelColor(uint32_t position)
{
    int32_t diameter = job.x[1] - job.x[0] + 1;
    int32_t radius = (diameter - 1) / 2;
    int32_t x = (int32_t)(position % diameter) - radius;
    int32_t y = (int32_t)(position / diameter) - radius;
    int32_t distance2 = x * x + y * y;
    int32_t inner = radius - Max(radius / 7, 2);
    int32_t hub = radius / 4;
    int32_t spoke = Max(radius / 10, 1);

    if (distance2 > radius * radius) return job.background;

    /* Inverse rotation: two integer dot products per pixel. Trigonometry
     * is evaluated only once, when the drawing request is accepted.
     */
    int32_t local_x = (x * job.cosine + y * job.sine) / 1024;
    int32_t local_y = (-x * job.sine + y * job.cosine) / 1024;

    if (distance2 >= inner * inner) {
        if (local_y < 0 && Abs(local_x) <= spoke) return job.accent;
        return job.color;
    }
    if (distance2 <= hub * hub) return job.color;
    if (Abs(local_y) <= spoke || (local_y > 0 && Abs(local_x) <= spoke))
        return job.color;
    return job.background;
}

static uint16_t AssetPixel(int32_t x, int32_t y)
{
    const GraphicAsset *asset = job.asset;
    if (x < 0 || y < 0 || x >= asset->width || y >= asset->height)
        return job.background;
    uint8_t pixel = asset->data[y * asset->stride + x];
    uint32_t alpha = pixel & 0x0FU;
    if (alpha == 0) return job.background;
    uint16_t color = job.asset_tinted ? job.color : asset->palette[pixel >> 4];
    if (alpha == 15) return color;

    /* Composite before interpolation, so transparent RGB cannot create halos. */
    uint32_t background = 15U - alpha;
    uint32_t red = (((color >> 11) & 31U) * alpha +
                    ((job.background >> 11) & 31U) * background + 7U) / 15U;
    uint32_t green = (((color >> 5) & 63U) * alpha +
                      ((job.background >> 5) & 63U) * background + 7U) / 15U;
    uint32_t blue = ((color & 31U) * alpha +
                     (job.background & 31U) * background + 7U) / 15U;
    return (uint16_t)((red << 11) | (green << 5) | blue);
}

static uint16_t AssetColor(uint32_t position)
{
    const GraphicAsset *asset = job.asset;
    int32_t side = job.x[1] - job.x[0] + 1;
    /* Doubled coordinates preserve half-pixel centers for even image sizes. */
    int32_t dx = 2 * (int32_t)(position % side) - (side - 1);
    int32_t dy = 2 * (int32_t)(position / side) - (side - 1);
    int32_t sx = dx * job.cosine + dy * job.sine + (asset->width - 1) * 1024;
    int32_t sy = -dx * job.sine + dy * job.cosine + (asset->height - 1) * 1024;
    if (sx <= -2048 || sy <= -2048 ||
        sx >= asset->width * 2048 || sy >= asset->height * 2048)
        return job.background;

    /* Floor also for negative coordinates, then fractions in 1/256 steps.
     * Four weights sum to 65536. Interpolate RGB565 channels independently,
     * rounding only once; mixing packed RGB565 words would corrupt colors.
     */
    int32_t x = FloorDivide(sx, 2048);
    int32_t y = FloorDivide(sy, 2048);
    uint32_t fx = (sx - x * 2048) >> 3;
    uint32_t fy = (sy - y * 2048) >> 3;
    uint16_t colors[4] = {
        AssetPixel(x, y), AssetPixel(x + 1, y),
        AssetPixel(x, y + 1), AssetPixel(x + 1, y + 1)
    };
    uint32_t weights[4] = {
        (256U - fx) * (256U - fy), fx * (256U - fy),
        (256U - fx) * fy, fx * fy
    };
    uint32_t red = 0, green = 0, blue = 0;
    for (uint8_t i = 0; i < 4; i++) {
        red += ((colors[i] >> 11) & 31U) * weights[i];
        green += ((colors[i] >> 5) & 63U) * weights[i];
        blue += (colors[i] & 31U) * weights[i];
    }
    return (uint16_t)((((red + 32768U) >> 16) << 11) |
                      (((green + 32768U) >> 16) << 5) |
                      ((blue + 32768U) >> 16));
}

/* Coordinates use eighths of a pixel. Only the one-pixel boundary band
 * needs the 4x4 samples; solid interior/exterior pixels take a fast path.
 */
static uint32_t DiskCoverage(int32_t x, int32_t y, int32_t radius)
{
    if (radius <= 0) return 0;
    int64_t distance = (int64_t)x * x + (int64_t)y * y;
    if (radius >= 6 && distance <= (int64_t)(radius - 6) * (radius - 6)) return 16;
    if (distance >= (int64_t)(radius + 6) * (radius + 6)) return 0;
    uint32_t coverage = 0;
    for (int32_t sy = -3; sy <= 3; sy += 2) {
        for (int32_t sx = -3; sx <= 3; sx += 2) {
            int64_t dx = x + sx, dy = y + sy;
            if (dx * dx + dy * dy <= (int64_t)radius * radius) coverage++;
        }
    }
    return coverage;
}

/* All weights sum to 16: accumulate RGB channels before rounding once. */
static uint16_t ShapeColor(uint32_t border, uint32_t fill, uint32_t background)
{
    uint32_t red = (((job.color >> 11) & 31U) * border +
                    ((job.accent >> 11) & 31U) * fill +
                    ((job.background >> 11) & 31U) * background + 8U) / 16U;
    uint32_t green = (((job.color >> 5) & 63U) * border +
                      ((job.accent >> 5) & 63U) * fill +
                      ((job.background >> 5) & 63U) * background + 8U) / 16U;
    uint32_t blue = ((job.color & 31U) * border + (job.accent & 31U) * fill +
                     (job.background & 31U) * background + 8U) / 16U;
    return (uint16_t)((red << 11) | (green << 5) | blue);
}

static uint32_t RoundedCoverage(int32_t x, int32_t y, int32_t w,
                                int32_t h, int32_t radius)
{
    if (x < 0 || y < 0 || x >= w || y >= h) return 0;
    if (radius == 0) return 16;
    /* Straight edges are aligned to pixel boundaries and need no sampling. */
    if ((x >= radius && x < w - radius) ||
        (y >= radius && y < h - radius)) return 16;
    int32_t cx = x < radius ? radius * 8 : (w - radius) * 8;
    int32_t cy = y < radius ? radius * 8 : (h - radius) * 8;
    return DiskCoverage(x * 8 + 4 - cx, y * 8 + 4 - cy, radius * 8);
}

static uint16_t RoundedRectangleColor(uint32_t position)
{
    int32_t w = job.x[1] - job.x[0] + 1;
    int32_t h = job.y[1] - job.y[0] + 1;
    int32_t x = position % w, y = position / w;
    uint32_t outer = RoundedCoverage(x, y, w, h, job.radius);
    uint32_t inner = RoundedCoverage(x - 1, y - 1, w - 2, h - 2, job.radius - 1);
    return ShapeColor(outer - inner, inner, 16U - outer);
}

static uint16_t ProgressBarColor(uint32_t position)
{
    int32_t w = job.x[1] - job.x[0] + 1;
    int32_t h = job.y[1] - job.y[0] + 1;
    int32_t x = position % w, y = position / w;
    uint32_t outer = RoundedCoverage(x, y, w, h, job.radius);
    uint32_t fill = RoundedCoverage(x, y, job.field_width, h,
                                    Min(job.radius, job.field_width / 2));
    if (fill > outer) fill = outer;
    return ShapeColor(fill, outer - fill, 16U - outer);
}

static int32_t GraphY(int32_t value)
{
    const ST7789_Graph *graph = job.graph;
    value = Max(graph->minimum, Min(value, graph->maximum));
    return (graph->maximum - value) * (graph->height - 1) /
           (graph->maximum - graph->minimum);
}

static uint16_t GraphColor(uint32_t position)
{
    const ST7789_Graph *graph = job.graph;
    int32_t x = position % graph->width, y = position / graph->width;
    uint16_t color = graph->background;
    /* Five horizontal/vertical grid lines, drawn with the curves in one pass. */
    bool horizontal = false, vertical = false;
    for (int32_t i = 0; i <= 4; i++) {
        if (y == i * (graph->height - 1) / 4) horizontal = true;
        if (x == i * (graph->width - 1) / 4) vertical = true;
    }
    if ((horizontal && x % 4 < 2) || (vertical && y % 4 < 2)) color = graph->grid;

    int32_t index = x - (graph->width - job.graph_count);
    if (index < 0) return color;
    const ST7789_GraphSample *current = &job.graph_samples[index];
    const ST7789_GraphSample *previous = index == 0 ? current : current - 1;
    int32_t a0 = GraphY(previous->a), a1 = GraphY(current->a);
    bool on_a = y >= Min(a0, a1) && y <= Max(a0, a1);
    if (on_a) color = graph->color_a;
    if (graph->series_count == 2) {
        int32_t b0 = GraphY(previous->b), b1 = GraphY(current->b);
        if (y >= Min(b0, b1) && y <= Max(b0, b1)) {
            /* Coincident curves alternate colors instead of hiding series A. */
            color = on_a && (x / 4) % 2 == 0 ? graph->color_a : graph->color_b;
        }
    }
    return color;
}

static uint16_t CircleColor(uint32_t position)
{
    if (job.radius == 0) return job.color;
    int32_t width = window.x1 - window.x0 + 1;
    int32_t x = ((int32_t)(position % width) + window.x0 - job.x[0]) * 8;
    int32_t y = ((int32_t)(position / width) + window.y0 - job.y[0]) * 8;
    int32_t radius = job.radius * 8 + 4;
    uint32_t coverage = DiskCoverage(x, y, radius);
    if (job.kind == CIRCLE) coverage -= DiskCoverage(x, y, radius - 8);
    return ShapeColor(coverage, 0, 16U - coverage);
}

/* Compose coverage directly in the unpublished DMA block, then map it to
 * RGB565. Overlapping glyphs keep the strongest coverage. The buffer is only
 * published after conversion, so DMA never sees intermediate coverage values.
 */
static void PrepareTextPixels(uint8_t *data, uint16_t pixels)
{
    for (uint16_t i = 0; i < pixels; i++) data[2U * i] = 0;
    int32_t width = window.x1 - window.x0 + 1;
    int32_t first_row = source_offset / width;
    int32_t last_row = (source_offset + pixels - 1) / width;
    int32_t pen = job.text_offset;
    for (const char *p = job.line_start; p != job.line_end; p++) {
        const FontGlyph *glyph = TextGlyph(job.font, (unsigned char)*p);
        int32_t advance = glyph->advance;
        int32_t gx = pen + glyph->x_offset;
        if (job.number_cell != 0) {
            advance = NumberAdvance(job.font, (unsigned char)*p, job.number_cell);
            gx = pen + (advance - glyph->width) / 2;
        }
        int32_t gy = glyph->y_offset;
        int32_t stride = (glyph->width + 1U) / 2U;
        int32_t y0 = Max(first_row, gy);
        int32_t y1 = Min(last_row, gy + glyph->height - 1);
        for (int32_t y = y0; y <= y1; y++) {
            int32_t x0 = Max(Max(gx, 0), (int32_t)source_offset - y * width);
            int32_t x1 = Min(Min(gx + glyph->width, width),
                             (int32_t)(source_offset + pixels) - y * width);
            for (int32_t x = x0; x < x1; x++) {
                uint32_t column = x - gx;
                uint32_t offset = glyph->offset + (y - gy) * stride + column / 2U;
                uint8_t packed = job.font->data[offset];
                uint8_t coverage = (column & 1U) ? packed & 0x0FU : packed >> 4;
                uint32_t i = y * width + x - source_offset;
                if (coverage > data[2U * i]) data[2U * i] = coverage;
            }
        }
        pen += advance;
    }
    for (uint16_t i = 0; i < pixels; i++) {
        uint16_t color = job.text_palette[data[2U * i]];
        data[2U * i] = color >> 8;
        data[2U * i + 1U] = color;
    }
}

static void PreparePixels(uint8_t *data, uint16_t pixels)
{
    if (window.source == TEXT_PIXELS) {
        PrepareTextPixels(data, pixels);
        return;
    }
    for (uint16_t i = 0; i < pixels; i++) {
        uint32_t position = source_offset + i;
        if (window.source == IMAGE_BYTES) {
            /* Preserve the original API's preformatted SPI byte order. */
            data[2U * i] = job.image[2U * position];
            data[2U * i + 1U] = job.image[2U * position + 1U];
            continue;
        }
        uint16_t color = job.color;
        if (window.source == HORIZONTAL_GRADIENT) color = GradientColor(position);
        if (window.source == WHEEL_PIXELS) color = WheelColor(position);
        if (window.source == ASSET_PIXELS) color = AssetColor(position);
        if (window.source == ROUNDED_PIXELS) color = RoundedRectangleColor(position);
        if (window.source == PROGRESS_PIXELS) color = ProgressBarColor(position);
        if (window.source == GRAPH_PIXELS) color = GraphColor(position);
        if (window.source == CIRCLE_PIXELS) color = CircleColor(position);
        data[2U * i] = (uint8_t)(color >> 8);
        data[2U * i + 1U] = (uint8_t)color;
    }
}

/* Called under a short critical section; never prepares pixels or commands. */
static void StartReadyBuffer(void)
{
    if (drawing_state != ST7789_STATE_BUSY || active_buffer >= 0) return;
    PixelBuffer *buffer = &buffers[send_index];
    if (buffer->state != READY) return;
    active_buffer = (int8_t)send_index;
    buffer->state = IN_FLIGHT;
    send_index ^= 1U;
    if (ST7789_TransportStartDMA(buffer->data, buffer->pixels * 2U) != HAL_OK)
        ST7789_GraphicsError();
}

bool ST7789_NeedsProcess(void)
{
	uint32_t mask = lock();
	bool pending = false;
	if (drawing_state == ST7789_STATE_BUSY) {
		pending = !window_active ||
			(active_buffer < 0 && buffers[send_index].state == READY) ||
			(remaining_pixels != 0 && buffers[prepare_index].state == FREE);
	}
	unlock(mask);
	return pending;
}

void ST7789_Process(void)
{
    if (drawing_state != ST7789_STATE_BUSY) return;
    if (!window_active) {
        int next = NextWindow();
        if (next == 0) {
            drawing_state = ST7789_STATE_IDLE;
            return;
        }
        if (next < 0) return;
        if (ST7789_BeginWindow(window.x0, window.y0, window.x1, window.y1) != ST7789_OK)
            return;
        buffers[0].state = buffers[1].state = FREE;
        prepare_index = send_index = 0;
        active_buffer = -1;
        total_pixels = (uint32_t)(window.x1 - window.x0 + 1U) *
                       (window.y1 - window.y0 + 1U);
        remaining_pixels = total_pixels;
        source_offset = completed_pixels = 0;
        window_active = 1;
        /* Tiny segments run only in main, not in a DMA completion interrupt. */
        if (total_pixels <= ST7789_BLOCKING_MAX_PIXELS && total_pixels <= ST7789_BUFFER_PIXELS) {
            PreparePixels(buffers[0].data, (uint16_t)total_pixels);
            if (ST7789_TransportPixelsBlocking(buffers[0].data,
                                              (uint16_t)(total_pixels * 2U)) != HAL_OK) {
                ST7789_GraphicsError();
                return;
            }
            ST7789_TransportEndPixels();
            window_active = 0;
            return;
        }
    }

    uint32_t mask = lock();
    StartReadyBuffer();
    if (drawing_state != ST7789_STATE_BUSY || !window_active || remaining_pixels == 0 ||
        buffers[prepare_index].state != FREE) {
        unlock(mask);
        return;
    }
    PixelBuffer *buffer = &buffers[prepare_index];
    uint16_t pixels = remaining_pixels > ST7789_BUFFER_PIXELS ?
                      ST7789_BUFFER_PIXELS : (uint16_t)remaining_pixels;
    buffer->state = FILLING;
    unlock(mask);

    PreparePixels(buffer->data, pixels);

    mask = lock();
    if (drawing_state == ST7789_STATE_BUSY) {
        buffer->pixels = pixels;
        source_offset += pixels;
        remaining_pixels -= pixels;
        buffer->state = READY;
        prepare_index ^= 1U;
        StartReadyBuffer();
    }
    unlock(mask);
}

void ST7789_PixelsCompleteISR(void)
{
    uint32_t mask = lock();
    if (drawing_state == ST7789_STATE_BUSY && active_buffer >= 0) {
        PixelBuffer *buffer = &buffers[(uint8_t)active_buffer];
        completed_pixels += buffer->pixels;
        buffer->state = FREE;
        active_buffer = -1;
        if (completed_pixels == total_pixels) {
            ST7789_TransportEndPixels();
            /* Main selects the next window, or publishes IDLE at end of job. */
            window_active = 0;
        } else {
            StartReadyBuffer();
        }
    }
    unlock(mask);
}

void ST7789_PixelsErrorISR(void)
{
    uint32_t mask = lock();
    if (drawing_state == ST7789_STATE_BUSY) ST7789_GraphicsError();
    unlock(mask);
}

ST7789_Result ST7789_Fill(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t color)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (x0 > x1 || y0 > y1 || !OnScreen(x1, y1)) return ST7789_INVALID_ARGUMENT;
    NewJob(FILL, color);
    job.x[0] = x0; job.y[0] = y0; job.x[1] = x1; job.y[1] = y1;
    return ST7789_OK;
}

ST7789_Result ST7789_Fill_Color(uint16_t color)
{
    return ST7789_Fill(0, 0, ST7789_WIDTH - 1, ST7789_HEIGHT - 1, color);
}

ST7789_Result ST7789_FillHorizontalGradient(uint16_t edge_color, uint16_t center_color)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    NewJob(GRADIENT, edge_color);
    job.background = center_color;
    job.x[0] = job.y[0] = 0;
    job.x[1] = ST7789_WIDTH - 1U;
    job.y[1] = ST7789_HEIGHT - 1U;
    return ST7789_OK;
}

ST7789_Result ST7789_DrawPixel(uint16_t x, uint16_t y, uint16_t color)
{
    return ST7789_Fill(x, y, x, y, color);
}

ST7789_Result ST7789_DrawSteeringWheel(uint16_t x, uint16_t y, uint16_t diameter,
                                      int16_t angle_deci_deg, uint16_t color,
                                      uint16_t accent, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (!OnScreen(x, y) || diameter < 16 || diameter > ST7789_WIDTH - x ||
        diameter > ST7789_HEIGHT - y) return ST7789_INVALID_ARGUMENT;

    float radians = angle_deci_deg * (3.14159265f / 1800.0f);
    NewJob(WHEEL, color);
    job.x[0] = x; job.y[0] = y;
    job.x[1] = x + diameter - 1; job.y[1] = y + diameter - 1;
    job.cosine = (int32_t)(cosf(radians) * 1024.0f);
    job.sine = (int32_t)(sinf(radians) * 1024.0f);
    job.accent = accent;
    job.background = background;
    return ST7789_OK;
}

ST7789_Result ST7789_DrawAsset(uint16_t x, uint16_t y, GraphicAssetId asset,
                              int16_t angle_deci_deg, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if ((unsigned)asset == ASSET_INVALID || (unsigned)asset >= ASSET_COUNT)
        return ST7789_INVALID_ARGUMENT;
    const GraphicAsset *info = &Assets[asset];
    uint16_t side = Max(info->width, info->height);
    if (!OnScreen(x, y) || side > ST7789_WIDTH - x || side > ST7789_HEIGHT - y)
        return ST7789_INVALID_ARGUMENT;

    float radians = angle_deci_deg * (3.14159265f / 1800.0f);
    NewJob(INDEXED_ASSET, 0);
    job.asset = info;
    job.background = background;
    job.x[0] = x; job.y[0] = y;
    job.x[1] = x + side - 1; job.y[1] = y + side - 1;
    job.cosine = (int32_t)(cosf(radians) * 1024.0f);
    job.sine = (int32_t)(sinf(radians) * 1024.0f);
    return ST7789_OK;
}

/* Monochrome symbols reuse the asset alpha and ignore its original palette. */
ST7789_Result ST7789_DrawSymbol(uint16_t x, uint16_t y, GraphicAssetId asset,
                               uint16_t color, uint16_t background)
{
    ST7789_Result result = ST7789_DrawAsset(x, y, asset, 0, background);
    if (result == ST7789_OK) {
        job.asset_tinted = 1;
        job.color = color;
    }
    return result;
}

ST7789_Result ST7789_DrawRoundedRectangle(uint16_t x, uint16_t y, uint16_t w,
    uint16_t h, uint16_t radius, uint16_t border, uint16_t fill, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (!OnScreen(x, y) || w < 3 || h < 3 || radius < 1 ||
        2U * radius >= w || 2U * radius >= h ||
        w > ST7789_WIDTH - x || h > ST7789_HEIGHT - y)
        return ST7789_INVALID_ARGUMENT;
    NewJob(ROUNDED_RECTANGLE, border);
    job.x[0] = x; job.y[0] = y;
    job.x[1] = x + w - 1; job.y[1] = y + h - 1;
    job.radius = radius;
    job.accent = fill;
    job.background = background;
    return ST7789_OK;
}

ST7789_Result ST7789_DrawProgressBar(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                                    uint16_t filled, uint16_t color,
                                    uint16_t track, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (!OnScreen(x, y) || w < h || h < 2 ||
        w > ST7789_WIDTH - x || h > ST7789_HEIGHT - y)
        return ST7789_INVALID_ARGUMENT;
    NewJob(PROGRESS_BAR, color);
    job.x[0] = x; job.y[0] = y;
    job.x[1] = x + w - 1; job.y[1] = y + h - 1;
    job.field_width = Min(filled, w);
    job.radius = h / 2;
    job.accent = track;
    job.background = background;
    return ST7789_OK;
}

ST7789_Result ST7789_DrawGraph(const ST7789_Graph *graph,
                               const ST7789_GraphSample *samples, uint16_t count)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (graph == NULL || (count != 0 && samples == NULL)) return ST7789_INVALID_ARGUMENT;
    if (!OnScreen(graph->x, graph->y) || graph->width < 2 || graph->height < 2 ||
        graph->width > ST7789_WIDTH - graph->x || graph->height > ST7789_HEIGHT - graph->y ||
        graph->minimum >= graph->maximum || count > graph->width ||
        graph->series_count < 1 || graph->series_count > 2)
        return ST7789_INVALID_ARGUMENT;
    NewJob(GRAPH, 0);
    job.graph = graph;
    job.graph_samples = samples;
    job.graph_count = count;
    job.x[0] = graph->x; job.y[0] = graph->y;
    job.x[1] = graph->x + graph->width - 1;
    job.y[1] = graph->y + graph->height - 1;
    return ST7789_OK;
}

ST7789_Result ST7789_DrawPixel_4px(uint16_t x, uint16_t y, uint16_t color)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (x == 0 || y == 0 || !OnScreen(x, y)) return ST7789_INVALID_ARGUMENT;
    /* Preserve the original primitive's actual 3x3 footprint. */
    return ST7789_Fill(x - 1, y - 1, Min(x + 1, ST7789_WIDTH - 1),
                       Min(y + 1, ST7789_HEIGHT - 1), color);
}

ST7789_Result ST7789_DrawFilledRectangle(uint16_t x, uint16_t y, uint16_t w,
                                        uint16_t h, uint16_t color)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (!OnScreen(x, y) || w == 0 || h == 0) return ST7789_INVALID_ARGUMENT;
    if (w > ST7789_WIDTH - x) w = ST7789_WIDTH - x;
    if (h > ST7789_HEIGHT - y) h = ST7789_HEIGHT - y;
    return ST7789_Fill(x, y, x + w - 1, y + h - 1, color);
}

ST7789_Result ST7789_DrawLine(uint16_t x0, uint16_t y0, uint16_t x1,
                             uint16_t y1, uint16_t color)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (!OnScreen(x0, y0) || !OnScreen(x1, y1)) return ST7789_INVALID_ARGUMENT;
    NewJob(LINE, color);
    InitLine(x0, y0, x1, y1);
    return ST7789_OK;
}

ST7789_Result ST7789_DrawRectangle(uint16_t x0, uint16_t y0, uint16_t x1,
                                  uint16_t y1, uint16_t color)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (x0 > x1 || y0 > y1 || !OnScreen(x1, y1)) return ST7789_INVALID_ARGUMENT;
    NewJob(RECTANGLE, color);
    job.x[0] = x0; job.y[0] = y0; job.x[1] = x1; job.y[1] = y1;
    return ST7789_OK;
}

static ST7789_Result CircleJob(int32_t x, int32_t y, int32_t radius,
                               uint16_t color, uint16_t background, JobKind kind)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (radius < 0 || x + radius < 0 || y + radius < 0 ||
        x - radius >= (int32_t)ST7789_WIDTH || y - radius >= (int32_t)ST7789_HEIGHT)
        return ST7789_INVALID_ARGUMENT;
    NewJob(kind, color);
    job.x[0] = x; job.y[0] = y; job.radius = radius;
    job.background = background;
    job.accent = color;
    return ST7789_OK;
}

ST7789_Result ST7789_DrawCircle(uint16_t x, uint16_t y, uint8_t radius, uint16_t color, uint16_t background)
{
    return CircleJob(x, y, radius, color, background, CIRCLE);
}

ST7789_Result ST7789_DrawFilledCircle(int16_t x, int16_t y, int16_t radius, uint16_t color, uint16_t background)
{
    return CircleJob(x, y, radius, color, background, FILLED_CIRCLE);
}

static ST7789_Result TriangleJob(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1,
                                 uint16_t x2, uint16_t y2, uint16_t color, JobKind kind)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (!OnScreen(x0, y0) || !OnScreen(x1, y1) || !OnScreen(x2, y2))
        return ST7789_INVALID_ARGUMENT;
    NewJob(kind, color);
    job.x[0] = x0; job.y[0] = y0; job.x[1] = x1; job.y[1] = y1;
    job.x[2] = x2; job.y[2] = y2;
    job.row = Min(y0, Min(y1, y2));
    InitLine(x0, y0, x1, y1);
    /* A filled collinear triangle becomes its longest segment. */
    int32_t area = ((int32_t)x1 - x0) * ((int32_t)y2 - y0) -
                   ((int32_t)x2 - x0) * ((int32_t)y1 - y0);
    if (kind == FILLED_TRIANGLE && area == 0) {
        int32_t longest = -1;
        for (uint8_t a = 0; a < 3; a++) {
            uint8_t b = (a + 1U) % 3U;
            int32_t dx = job.x[b] - job.x[a], dy = job.y[b] - job.y[a];
            if (dx * dx + dy * dy > longest) {
                longest = dx * dx + dy * dy;
                InitLine(job.x[a], job.y[a], job.x[b], job.y[b]);
            }
        }
        job.kind = LINE;
    }
    return ST7789_OK;
}

ST7789_Result ST7789_DrawTriangle(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1,
                                 uint16_t x2, uint16_t y2, uint16_t color)
{
    return TriangleJob(x0, y0, x1, y1, x2, y2, color, TRIANGLE);
}

ST7789_Result ST7789_DrawFilledTriangle(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1,
                                       uint16_t x2, uint16_t y2, uint16_t color)
{
    return TriangleJob(x0, y0, x1, y1, x2, y2, color, FILLED_TRIANGLE);
}

ST7789_Result ST7789_DrawImage(uint16_t x, uint16_t y, uint16_t w,
                              uint16_t h, const uint16_t *data)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (data == NULL || !OnScreen(x, y) || w == 0 || h == 0 ||
        w > ST7789_WIDTH - x || h > ST7789_HEIGHT - y) return ST7789_INVALID_ARGUMENT;
    NewJob(IMAGE, 0);
    job.x[0] = x; job.y[0] = y; job.x[1] = x + w - 1; job.y[1] = y + h - 1;
    job.image = (const uint8_t *)data;
    return ST7789_OK;
}

ST7789_Result ST7789_WriteString(uint16_t x, uint16_t y, const char *text,
                                FontId font, uint16_t color, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (text == NULL || !OnScreen(x, y) || (unsigned)font >= FONT_COUNT)
        return ST7789_INVALID_ARGUMENT;
    ST7789_TextSize size;
    if (ST7789_MeasureText(text, font, &size) != ST7789_OK ||
        Fonts[font].height > ST7789_HEIGHT - y) return ST7789_INVALID_ARGUMENT;
    for (const char *p = text; *p != '\0'; p++) {
        if (*p == '\n') continue;
        TextLine glyph_line = AppendGlyph((TextLine){0}, TextGlyph(&Fonts[font], (unsigned char)*p));
        if (glyph_line.right - glyph_line.left > ST7789_WIDTH) return ST7789_INVALID_ARGUMENT;
    }
	if (!CopyText(text)) return ST7789_INVALID_ARGUMENT;
    NewJob(TEXT, color);
	job.text = job.text_buffer;
    job.font = &Fonts[font];
    job.field_width = 0;
    job.background = background;
    PrepareTextPalette();
    job.text_x = x; job.text_y = y;
    return ST7789_OK;
}

ST7789_Result ST7789_WriteTextField(uint16_t x, uint16_t y, uint16_t width,
    const char *text, FontId font, ST7789_TextAlign align, uint16_t color, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    ST7789_TextSize size;
    if (!OnScreen(x, y) || width == 0 || width > ST7789_WIDTH - x ||
        (unsigned)align > ST7789_TEXT_RIGHT ||
        ST7789_MeasureText(text, font, &size) != ST7789_OK)
        return ST7789_INVALID_ARGUMENT;
    if (Fonts[font].height > ST7789_HEIGHT - y || size.width > width)
        return ST7789_INVALID_ARGUMENT;
    for (const char *p = text; *p != '\0'; p++)
        if (*p == '\n') return ST7789_INVALID_ARGUMENT;
	if (!CopyText(text)) return ST7789_INVALID_ARGUMENT;
    NewJob(TEXT, color);
	job.text = job.text_buffer;
    job.font = &Fonts[font];
    job.field_width = width;
    job.text_align = align;
    job.background = background;
    PrepareTextPalette();
    job.text_x = x;
    job.text_y = y;
    return ST7789_OK;
}

ST7789_Result ST7789_WriteNumberField(uint16_t x, uint16_t y, uint16_t width,
    const char *number, FontId font, uint16_t color, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (number == NULL || !OnScreen(x, y) || width == 0 ||
        width > ST7789_WIDTH - x || (unsigned)font >= FONT_COUNT)
        return ST7789_INVALID_ARGUMENT;
    const FontInfo *info = &Fonts[font];
    if (info->height > ST7789_HEIGHT - y) return ST7789_INVALID_ARGUMENT;

    /* One slot wide enough for every digit and sign, computed once per job. */
    uint16_t cell = 0;
    const char *symbols = "0123456789+-";
    for (const char *p = symbols; *p != '\0'; p++) {
        if (*p < info->first_char || *p > info->last_char)
            return ST7789_INVALID_ARGUMENT;
        const FontGlyph *glyph = TextGlyph(info, (unsigned char)*p);
        cell = Max(cell, Max(glyph->advance, glyph->width));
    }
    if ('.' < info->first_char || '.' > info->last_char) return ST7789_INVALID_ARGUMENT;
    uint32_t number_width = 0;
    for (const char *p = number; *p != '\0'; p++) {
        if (!(*p >= '0' && *p <= '9') && *p != '+' && *p != '-' && *p != '.')
            return ST7789_INVALID_ARGUMENT;
        number_width += NumberAdvance(info, (unsigned char)*p, cell);
    }
    if (number_width > width) return ST7789_INVALID_ARGUMENT;

	if (!CopyText(number)) return ST7789_INVALID_ARGUMENT;
    NewJob(TEXT, color);
	job.text = job.text_buffer;
    job.font = info;
    job.field_width = width;
    job.number_cell = cell;
    job.background = background;
    PrepareTextPalette();
    job.text_x = x;
    job.text_y = y;
    return ST7789_OK;
}

ST7789_Result ST7789_WriteChar(uint16_t x, uint16_t y, char ch,
                              FontId font, uint16_t color, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (ch == '\0') return ST7789_INVALID_ARGUMENT;
    char text[2] = {ch, '\0'};
	return ST7789_WriteString(x, y, text, font, color, background);
}
