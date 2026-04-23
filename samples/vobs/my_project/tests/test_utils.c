/*
 * test_utils.c  --  unit tests for utils.c
 *
 * VERSION: /main/2   LABEL: REL_2_1
 * Author:  mary.jones   Date: 2024-05-21.09:00:00
 *
 * $Header: /vobs/my_project/tests/test_utils.c@@/main/2  2024-05-21.09:00:00  mary.jones  $
 */

#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "utils.h"
#include "config.h"

/* ---- test helpers ------------------------------------------------------ */
static int g_passed = 0;
static int g_failed = 0;

#define TEST(name, expr)                                        \
    do {                                                        \
        if (expr) {                                             \
            printf("  PASS  %s\n", name);                      \
            g_passed++;                                         \
        } else {                                                \
            printf("  FAIL  %s  (line %d)\n", name, __LINE__); \
            g_failed++;                                         \
        }                                                       \
    } while (0)

/* ---- str_copy ---------------------------------------------------------- */
static void test_str_copy(void)
{
    char buf[16];
    printf("str_copy:\n");

    str_copy(buf, "hello", sizeof(buf));
    TEST("basic copy",          strcmp(buf, "hello") == 0);

    str_copy(buf, "abcdefghijklmnop", 5);   /* truncate */
    TEST("truncation",          strcmp(buf, "abcd") == 0);

    str_copy(buf, "", sizeof(buf));
    TEST("empty src",           buf[0] == '\0');

    TEST("null dst no crash",   str_copy(NULL, "x", 4) == NULL);
    TEST("null src no crash",   str_copy(buf,  NULL, 4) == buf);
}

/* ---- str_trim ---------------------------------------------------------- */
static void test_str_trim(void)
{
    char s1[] = "  hello  ";
    char s2[] = "\t\n world \t";
    char s3[] = "nospace";
    char s4[] = "   ";

    printf("str_trim:\n");
    TEST("leading+trailing spaces",  strcmp(str_trim(s1), "hello") == 0);
    TEST("tab/newline whitespace",   strcmp(str_trim(s2), "world") == 0);
    TEST("no whitespace",            strcmp(str_trim(s3), "nospace") == 0);
    TEST("all whitespace → empty",   str_trim(s4)[0] == '\0');
    TEST("null ptr no crash",        str_trim(NULL) == NULL);
}

/* ---- circ_buf ---------------------------------------------------------- */
static void test_circ_buf(void)
{
    circ_buf_t cb;
    uint8_t    storage[4];
    uint8_t    out;

    printf("circ_buf:\n");

    TEST("init ok",     circ_buf_init(&cb, storage, 4) == STATUS_OK);
    TEST("empty avail", circ_buf_available(&cb) == 0);

    TEST("push 1",      circ_buf_push(&cb, 0xAA) == STATUS_OK);
    TEST("push 2",      circ_buf_push(&cb, 0xBB) == STATUS_OK);
    TEST("push 3",      circ_buf_push(&cb, 0xCC) == STATUS_OK);
    TEST("push 4",      circ_buf_push(&cb, 0xDD) == STATUS_OK);
    TEST("avail = 4",   circ_buf_available(&cb) == 4);
    TEST("push full",   circ_buf_push(&cb, 0xFF) == STATUS_ERROR);

    TEST("pop 1=0xAA",  circ_buf_pop(&cb, &out) == STATUS_OK && out == 0xAA);
    TEST("pop 2=0xBB",  circ_buf_pop(&cb, &out) == STATUS_OK && out == 0xBB);
    TEST("avail = 2",   circ_buf_available(&cb) == 2);

    circ_buf_reset(&cb);
    TEST("reset avail=0", circ_buf_available(&cb) == 0);
    TEST("pop empty",     circ_buf_pop(&cb, &out) == STATUS_ERROR);
}

/* ---- safe_memcpy ------------------------------------------------------- */
static void test_safe_memcpy(void)
{
    char src[] = "hello";
    char dst[8] = {0};

    printf("safe_memcpy:\n");
    TEST("normal copy",   safe_memcpy(dst, 8, src, 6) == STATUS_OK);
    TEST("content ok",    strcmp(dst, "hello") == 0);
    TEST("overflow → err", safe_memcpy(dst, 3, src, 6) == STATUS_ERROR);
    TEST("null dst → err", safe_memcpy(NULL, 8, src, 6) == STATUS_ERROR);
    TEST("null src → err", safe_memcpy(dst, 8, NULL, 6) == STATUS_ERROR);
    TEST("zero len ok",    safe_memcpy(dst, 8, src, 0) == STATUS_OK);
}

/* ---- main -------------------------------------------------------------- */
int main(void)
{
    printf("=== utils unit tests ===\n\n");
    test_str_copy();
    test_str_trim();
    test_circ_buf();
    test_safe_memcpy();
    printf("\n=== Results: %d passed, %d failed ===\n", g_passed, g_failed);
    return g_failed ? 1 : 0;
}
