/* PackBits, the one hot loop in this library that Python cannot make fast.
 *
 * **The algorithm is a transliteration of `psd.py`'s, and it has to stay one.** PSD stores one PackBits stream per
 * scanline and the writer's byte output is what a drawing application accepts, so this file is not allowed to encode
 * *better* -- only faster. `tests/test_packbits_c.py` compares the two implementations byte for byte, and
 * `test_packbits_round_trips_the_cases_that_break_compressors` already states what a correct encoder has to survive.
 *
 * The row boundary is passed in rather than assumed: a run or a literal must not cross it, which is what makes 900
 * separate calls and one call with a row width the same bytes. Getting that wrong produces a stream that decodes into
 * the right bytes arranged the wrong way, and only on pictures with flat regions taller than a single row.
 *
 * Built with `gcc -shared -O2 -o _packbits.dll _packbits.c`; the library loads it with ctypes and falls back to the
 * Python encoder when it is absent, so an install without a compiler still writes correct files.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define MAX_RUN 128

static size_t pack_span(const uint8_t *data, size_t start, size_t end, uint8_t *out) {
    size_t written = 0;
    size_t index = start;
    while (index < end) {
        size_t run = 1;
        while (index + run < end && run < MAX_RUN && data[index + run] == data[index]) {
            run++;
        }
        if (run >= 2) {
            out[written++] = (uint8_t)(257 - run); /* a run: 1 - n, as a signed byte */
            out[written++] = data[index];
            index += run;
            continue;
        }
        /* otherwise gather literals until a run of three starts, which is where compressing becomes worthwhile */
        size_t literal = index;
        while (index < end && index - literal < MAX_RUN) {
            if (index + 2 < end && data[index] == data[index + 1] && data[index] == data[index + 2]) {
                break;
            }
            index++;
        }
        out[written++] = (uint8_t)(index - literal - 1);
        memcpy(out + written, data + literal, index - literal);
        written += index - literal;
    }
    return written;
}

/* Compress `length` bytes into rows of `width`, writing each row's compressed size into `counts`.
 *
 * Returns the number of blob bytes written, or 0 if `capacity` was too small -- 0 is not a legal result for a
 * non-empty channel, so the caller can tell the two apart without a second out-parameter. */
size_t lw_packbits_rows(const uint8_t *data, size_t length, size_t width,
                        uint8_t *out, size_t capacity, uint16_t *counts) {
    size_t written = 0;
    size_t row = 0;
    size_t span = width == 0 ? 1 : width;
    size_t start = 0;
    while (start < length) {
        size_t end = start + span;
        if (end > length) {
            end = length;
        }
        /* The worst case for one row is a header byte for every 128 bytes plus the bytes themselves. */
        size_t room = (end - start) + (end - start) / MAX_RUN + 2;
        if (written + room > capacity) {
            return 0;
        }
        size_t before = written;
        written += pack_span(data, start, end, out + written);
        if (written - before > 0xFFFF) {
            return 0; /* a row longer than the format's two-byte length cannot be described */
        }
        counts[row++] = (uint16_t)(written - before);
        start = end;
    }
    return written;
}

/* How many bytes `lw_packbits_rows` needs for this shape, so the caller can allocate once. */
size_t lw_packbits_capacity(size_t length, size_t width) {
    size_t span = width == 0 ? 1 : width;
    size_t rows = (length + span - 1) / span;
    return length + rows * 2 + (length / MAX_RUN) + 64;
}

/* The row count the shape implies -- the caller checks it against the layer's height. */
size_t lw_packbits_rows_for(size_t length, size_t width) {
    size_t span = width == 0 ? 1 : width;
    return (length + span - 1) / span;
}
