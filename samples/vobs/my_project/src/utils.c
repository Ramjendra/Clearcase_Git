/*
 * utils.c  --  utility functions
 *
 * ClearCase version history:
 *   /main/1  : str_copy, str_compare, str_length   (label: INITIAL_IMPORT)
 *   /main/2  : str_trim, str_split                 (label: REL_1_0)
 *   /main/3  : circ_buf_* circular buffer API      (label: REL_2_0)
 *   /main/4  : safe_memcpy                         (label: REL_2_1, SECURITY_FIX_001)
 *
 * ENCODING CORNER CASE: This file was originally edited on Windows with a
 * Western European locale. Some comments contain ISO-8859-1 characters
 * (e.g., the author name "Müller" and the copyright symbol ©).
 * The migration tool detects and converts to UTF-8.
 *
 * $Header: /vobs/my_project/src/utils.c@@/main/4  2024-05-20.11:45:00  build_svc  $
 * $Author: build_svc $
 * $Revision: 4 $
 */

#include <string.h>
#include <ctype.h>
#include "utils.h"
#include "config.h"

/* Original author: Klaus M\xfcller (ISO-8859-1: \xfc = ü)            */
/* Copyright \xa9 2023 MyCompany GmbH (ISO-8859-1: \xa9 = ©)          */

/* ---- version /main/1 --------------------------------------------------- */

char *str_copy(char *dst, const char *src, uint32_t max_len)
{
    uint32_t i = 0;
    if (!dst || !src || max_len == 0) {
        return dst;
    }
    while (i < max_len - 1 && src[i] != '\0') {
        dst[i] = src[i];
        i++;
    }
    dst[i] = '\0';
    return dst;
}

int str_compare(const char *a, const char *b)
{
    if (!a && !b) return  0;
    if (!a)       return -1;
    if (!b)       return  1;
    return strcmp(a, b);
}

int str_length(const char *s)
{
    if (!s) return 0;
    return (int)strlen(s);
}

/* ---- version /main/2 --------------------------------------------------- */

char *str_trim(char *s)
{
    char *end;
    if (!s) return s;
    while (isspace((unsigned char)*s)) s++;
    if (*s == '\0') return s;
    end = s + strlen(s) - 1;
    while (end > s && isspace((unsigned char)*end)) end--;
    end[1] = '\0';
    return s;
}

int str_split(char *s, char delim, char **parts, int max_parts)
{
    int count = 0;
    if (!s || !parts || max_parts <= 0) return 0;
    parts[count++] = s;
    while (*s && count < max_parts) {
        if (*s == delim) {
            *s = '\0';
            parts[count++] = s + 1;
        }
        s++;
    }
    return count;
}

/* ---- version /main/3: circular buffer ---------------------------------- */

status_t circ_buf_init(circ_buf_t *cb, uint8_t *storage, uint32_t capacity)
{
    if (!cb || !storage || capacity == 0) return STATUS_ERROR;
    cb->buf      = storage;
    cb->capacity = capacity;
    cb->head     = 0;
    cb->tail     = 0;
    cb->count    = 0;
    return STATUS_OK;
}

status_t circ_buf_push(circ_buf_t *cb, uint8_t byte)
{
    if (!cb) return STATUS_ERROR;
    if (cb->count == cb->capacity) return STATUS_ERROR;  /* full */
    cb->buf[cb->head] = byte;
    cb->head = (cb->head + 1) % cb->capacity;
    cb->count++;
    return STATUS_OK;
}

status_t circ_buf_pop(circ_buf_t *cb, uint8_t *out)
{
    if (!cb || !out) return STATUS_ERROR;
    if (cb->count == 0) return STATUS_ERROR;  /* empty */
    *out = cb->buf[cb->tail];
    cb->tail = (cb->tail + 1) % cb->capacity;
    cb->count--;
    return STATUS_OK;
}

uint32_t circ_buf_available(const circ_buf_t *cb)
{
    return cb ? cb->count : 0;
}

void circ_buf_reset(circ_buf_t *cb)
{
    if (!cb) return;
    cb->head = cb->tail = cb->count = 0;
}

/* ---- version /main/4: safe_memcpy (security fix) ----------------------- */

status_t safe_memcpy(void *dst, uint32_t dst_size,
                     const void *src, uint32_t src_len)
{
    if (!dst || !src)          return STATUS_ERROR;
    if (src_len > dst_size)    return STATUS_ERROR;  /* would overflow */
    memcpy(dst, src, src_len);
    return STATUS_OK;
}
