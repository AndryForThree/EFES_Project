#include "st7789_graphics.h"
#include "st7789_transport.h"

typedef enum { FREE, FILLING, READY, IN_FLIGHT } BufferState;
typedef enum { SOLID, IMAGE_BYTES, GLYPH, HORIZONTAL_GRADIENT } PixelSource;
typedef enum { FILL, LINE, RECTANGLE, CIRCLE, FILLED_CIRCLE,
               TRIANGLE, FILLED_TRIANGLE, IMAGE, TEXT, GRADIENT } JobKind;

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
    uint8_t stage, right_pending;
    int32_t right_x0, right_x1, right_y;
    LineCursor line;
    const uint8_t *image;
    const char *text;
    char character[2];
    struct { uint8_t width, height; const uint16_t *data; } font;
    int32_t text_x, text_y;
} DrawingJob;

typedef struct {
    uint16_t x0, y0, x1, y1;
    PixelSource source;
    uint8_t character;
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
    job.color = color;
    job.stage = 0;
    job.right_pending = 0;
    window_active = 0;
    drawing_state = ST7789_STATE_BUSY;
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

/* Fixed-cost integer square root: at most 16 iterations, no floating point. */
static uint32_t IntegerSqrt(uint32_t value)
{
    uint32_t root = 0, bit = 1UL << 30;
    while (bit != 0) {
        if (value >= root + bit) {
            value -= root + bit;
            root = (root >> 1) + bit;
        } else {
            root >>= 1;
        }
        bit >>= 2;
    }
    return root;
}

/* 1 = window ready, 0 = job done, -1 = bounded progress without a window. */
static int NextCircleWindow(void)
{
    if (job.right_pending) {
        job.right_pending = 0;
        return SolidWindow(job.right_x0, job.right_y, job.right_x1,
                           job.right_y) ? 1 : -1;
    }
    int32_t last_y = Min(job.y[0] + job.radius, ST7789_HEIGHT - 1);
    if (job.row > last_y) return 0;
    int32_t y = job.row++;
    int32_t dy = y - job.y[0];
    uint32_t dy2 = (uint32_t)(dy * dy);
    uint32_t radius2 = (uint32_t)(job.radius * job.radius);
    int32_t outer = (int32_t)IntegerSqrt(radius2 - dy2);
    if (job.kind == FILLED_CIRCLE || job.radius == 0 || Abs(dy) == job.radius)
        return SolidWindow(job.x[0] - outer, y, job.x[0] + outer, y) ? 1 : -1;

    /* A one-pixel radial ring: leave the disk of radius r-1 untouched. */
    int32_t inner_radius = job.radius - 1;
    int32_t inner = (int32_t)IntegerSqrt((uint32_t)(inner_radius * inner_radius) - dy2);
    job.right_x0 = job.x[0] + inner + 1;
    job.right_x1 = job.x[0] + outer;
    job.right_y = y;
    job.right_pending = 1;
    return SolidWindow(job.x[0] - outer, y, job.x[0] - inner - 1, y) ? 1 : -1;
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

static int NextTextWindow(void)
{
    unsigned char ch = (unsigned char)*job.text;
    if (ch == 0) return 0;
    job.text++;
    if (ch == '\n') {
        job.text_x = 0;
        job.text_y += job.font.height;
        return -1;
    }
    if (job.text_x + job.font.width > ST7789_WIDTH) {
        job.text_x = 0;
        job.text_y += job.font.height;
    }
    if (job.text_y + job.font.height > ST7789_HEIGHT) return 0;
    window.x0 = (uint16_t)job.text_x; window.y0 = (uint16_t)job.text_y;
    window.x1 = window.x0 + job.font.width - 1U;
    window.y1 = window.y0 + job.font.height - 1U;
    window.source = GLYPH;
    window.character = ch >= 32 && ch <= 126 ? ch : '?';
    job.text_x += job.font.width;
    return 1;
}

static int NextWindow(void)
{
    switch (job.kind) {
    case FILL:
    case IMAGE:
    case GRADIENT:
        if (job.stage++) return 0;
        SolidWindow(job.x[0], job.y[0], job.x[1], job.y[1]);
        if (job.kind == IMAGE) window.source = IMAGE_BYTES;
        if (job.kind == GRADIENT) window.source = HORIZONTAL_GRADIENT;
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
        return NextCircleWindow();
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

static void PreparePixels(uint8_t *data, uint16_t pixels)
{
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
        if (window.source == GLYPH) {
            uint32_t row = position / job.font.width;
            uint32_t col = position % job.font.width;
            uint16_t bits = job.font.data[(window.character - 32U) * job.font.height + row];
            color = (bits & (0x8000U >> col)) ? job.color : job.background;
        }
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

void ST7789_Process(void)
{
    if (drawing_state != ST7789_STATE_BUSY) return;
    if (!window_active) {
        int next = NextWindow();
        if (next == 0) { drawing_state = ST7789_STATE_IDLE; return; }
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

    uint32_t mask = ST7789_Lock();
    StartReadyBuffer();
    if (drawing_state != ST7789_STATE_BUSY || !window_active || remaining_pixels == 0 ||
        buffers[prepare_index].state != FREE) {
        ST7789_Unlock(mask);
        return;
    }
    PixelBuffer *buffer = &buffers[prepare_index];
    uint16_t pixels = remaining_pixels > ST7789_BUFFER_PIXELS ?
                      ST7789_BUFFER_PIXELS : (uint16_t)remaining_pixels;
    buffer->state = FILLING;
    ST7789_Unlock(mask);

    PreparePixels(buffer->data, pixels);

    mask = ST7789_Lock();
    if (drawing_state == ST7789_STATE_BUSY) {
        buffer->pixels = pixels;
        source_offset += pixels;
        remaining_pixels -= pixels;
        buffer->state = READY;
        prepare_index ^= 1U;
        StartReadyBuffer();
    }
    ST7789_Unlock(mask);
}

void ST7789_PixelsCompleteISR(void)
{
    uint32_t mask = ST7789_Lock();
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
    ST7789_Unlock(mask);
}

void ST7789_PixelsErrorISR(void)
{
    uint32_t mask = ST7789_Lock();
    if (drawing_state == ST7789_STATE_BUSY) ST7789_GraphicsError();
    ST7789_Unlock(mask);
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
                               uint16_t color, JobKind kind)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (radius < 0 || x + radius < 0 || y + radius < 0 ||
        x - radius >= (int32_t)ST7789_WIDTH || y - radius >= (int32_t)ST7789_HEIGHT)
        return ST7789_INVALID_ARGUMENT;
    NewJob(kind, color);
    job.x[0] = x; job.y[0] = y; job.radius = radius;
    job.row = Max(y - radius, 0);
    return ST7789_OK;
}

ST7789_Result ST7789_DrawCircle(uint16_t x, uint16_t y, uint8_t radius, uint16_t color)
{
    return CircleJob(x, y, radius, color, CIRCLE);
}

ST7789_Result ST7789_DrawFilledCircle(int16_t x, int16_t y, int16_t radius, uint16_t color)
{
    return CircleJob(x, y, radius, color, FILLED_CIRCLE);
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
                                FontDef font, uint16_t color, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if (text == NULL || !OnScreen(x, y) || font.data == NULL ||
        font.width == 0 || font.width > 16 || font.height == 0 ||
        font.height > ST7789_HEIGHT - y) return ST7789_INVALID_ARGUMENT;
    NewJob(TEXT, color);
    job.text = text;
    job.font.width = font.width;
    job.font.height = font.height;
    job.font.data = font.data;
    job.background = background;
    job.text_x = x; job.text_y = y;
    return ST7789_OK;
}

ST7789_Result ST7789_WriteChar(uint16_t x, uint16_t y, char ch,
                              FontDef font, uint16_t color, uint16_t background)
{
    ST7789_Result ready = ST7789_GraphicsReady();
    if (ready != ST7789_OK) return ready;
    if ((unsigned char)ch < 32 || (unsigned char)ch > 126)
        return ST7789_INVALID_ARGUMENT;
    ST7789_Result result = ST7789_WriteString(x, y, job.character, font, color, background);
    if (result == ST7789_OK) { job.character[0] = ch; job.character[1] = '\0'; }
    return result;
}
