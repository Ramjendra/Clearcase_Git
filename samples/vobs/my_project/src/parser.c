/*
 * parser.c  --  simple line-oriented config file parser
 *
 * ClearCase version history:
 *   /main/1  : initial parser, key=value only            (label: REL_1_0)
 *   /main/2  : add section support [section]             (label: REL_2_0)
 *   /main/rel3_feature/1 : add multi-line values         (no label)
 *   /main/rel3_feature/2 : add escape sequences          (no label)
 *   /main/3  : merge from rel3_feature                   (label: REL_3_0)
 *
 * CORNER CASES demonstrated in this file:
 *   1. @@-extended #include paths (both forms)
 *   2. Hard-coded /view/ path in a #define
 *   3. #pragma ident with ClearCase version string
 *   4. CC keyword expansion across all seven keywords
 *
 * $Header: /vobs/my_project/src/parser.c@@/main/3  2024-06-15.16:00:00  mary.jones  $
 * $Author: mary.jones $
 * $Date: 2024/06/15 16:00:00 $
 * $Locker:  $
 * $Revision: 3 $
 * $Source: /vobs/my_project/src/parser.c $
 * $State: Exp $
 */

/* CORNER CASE 1a: @@-extended angle-bracket include */
#include <stdio.h@@/main/2>
/* CORNER CASE 1b: @@-extended quote include */
#include "config.h@@/main/3"
#include "utils.h@@/main/4"

/* CORNER CASE 2: hard-coded /view/ path in a constant */
#define FALLBACK_SCHEMA_PATH \
    "/view/mary_dev_view/vobs/my_project/data/schema.ini"

/* CORNER CASE 3: Oracle/Sun #pragma ident with CC version embedded */
#pragma ident "@(#)parser.c  3  2024/06/15  my_project@@/main/3"

/* ---- types ------------------------------------------------------------- */
#define PARSER_MAX_LINE    512
#define PARSER_MAX_KEY      64
#define PARSER_MAX_VAL     256
#define PARSER_MAX_SECTION  32

typedef struct {
    char  section[PARSER_MAX_SECTION];
    char  key    [PARSER_MAX_KEY];
    char  value  [PARSER_MAX_VAL];
} parser_entry_t;

typedef void (*parser_callback_t)(const parser_entry_t *entry, void *ctx);

/* ---- version /main/1 --------------------------------------------------- */

static int is_comment(const char *line)
{
    return (line[0] == '#' || line[0] == ';');
}

static int parse_keyval(const char *line, char *key, char *val)
{
    const char *eq = strchr(line, '=');
    size_t      klen;
    if (!eq) return 0;
    klen = (size_t)(eq - line);
    if (klen == 0 || klen >= PARSER_MAX_KEY) return 0;
    str_copy(key, line, (uint32_t)klen + 1);
    str_trim(key);
    str_copy(val, eq + 1, PARSER_MAX_VAL);
    str_trim(val);
    return 1;
}

/* ---- version /main/2: section support ---------------------------------- */

static int parse_section(const char *line, char *section)
{
    const char *end;
    size_t      len;
    if (line[0] != '[') return 0;
    end = strchr(line, ']');
    if (!end) return 0;
    len = (size_t)(end - line - 1);
    if (len == 0 || len >= PARSER_MAX_SECTION) return 0;
    str_copy(section, line + 1, (uint32_t)len + 1);
    return 1;
}

int parser_load(const char *filepath,
                parser_callback_t cb, void *ctx)
{
    FILE          *fp;
    char           line[PARSER_MAX_LINE];
    parser_entry_t entry;
    char           cur_section[PARSER_MAX_SECTION] = "";

    fp = fopen(filepath, "r");
    if (!fp) {
        DBG_PRINT("Cannot open config: %s", filepath);
        return STATUS_ERROR;
    }

    while (fgets(line, sizeof(line), fp)) {
        str_trim(line);
        if (!line[0] || is_comment(line)) continue;

        if (parse_section(line, cur_section)) {
            str_copy(entry.section, cur_section, sizeof(entry.section));
            continue;
        }

        if (parse_keyval(line, entry.key, entry.value)) {
            str_copy(entry.section, cur_section, sizeof(entry.section));
            if (cb) cb(&entry, ctx);
        }
    }

    fclose(fp);
    return STATUS_OK;
}

/* ---- version /main/3 (merged from rel3_feature): multi-line & escapes -- */

static void unescape(char *s)
{
    char *r = s, *w = s;
    while (*r) {
        if (*r == '\\' && *(r+1)) {
            r++;
            switch (*r) {
                case 'n':  *w++ = '\n'; break;
                case 't':  *w++ = '\t'; break;
                case '\\': *w++ = '\\'; break;
                default:   *w++ = *r;   break;
            }
            r++;
        } else {
            *w++ = *r++;
        }
    }
    *w = '\0';
}

int parser_load_multiline(const char *filepath,
                           parser_callback_t cb, void *ctx)
{
    FILE          *fp;
    char           line[PARSER_MAX_LINE];
    char           cont[PARSER_MAX_VAL] = "";
    parser_entry_t entry;
    char           cur_section[PARSER_MAX_SECTION] = "";
    int            in_continuation = 0;

    fp = fopen(filepath, "r");
    if (!fp) return STATUS_ERROR;

    while (fgets(line, sizeof(line), fp)) {
        size_t len;
        str_trim(line);
        if (!line[0] || is_comment(line)) continue;

        len = strlen(line);
        if (len > 0 && line[len-1] == '\\') {
            line[len-1] = '\0';   /* strip continuation backslash */
            if (in_continuation) {
                strncat(cont, line, sizeof(cont) - strlen(cont) - 1);
            } else {
                str_copy(cont, line, sizeof(cont));
                in_continuation = 1;
            }
            continue;
        }

        if (in_continuation) {
            strncat(cont, line, sizeof(cont) - strlen(cont) - 1);
            unescape(cont);
            str_copy(entry.value, cont, sizeof(entry.value));
            str_copy(entry.section, cur_section, sizeof(entry.section));
            if (cb) cb(&entry, ctx);
            cont[0] = '\0';
            in_continuation = 0;
            continue;
        }

        if (parse_section(line, cur_section)) continue;
        if (parse_keyval(line, entry.key, entry.value)) {
            unescape(entry.value);
            str_copy(entry.section, cur_section, sizeof(entry.section));
            if (cb) cb(&entry, ctx);
        }
    }

    fclose(fp);
    return STATUS_OK;
}
