/*
 * utils.h -- utility function declarations
 *
 * ClearCase version history:
 *   /main/1  : initial declarations              (label: INITIAL_IMPORT)
 *   /main/2  : added str_trim, str_split         (label: REL_1_0)
 *   /main/3  : added circular buffer API         (label: REL_2_0)
 *   /main/4  : added safe_memcpy (security fix)  (label: REL_2_1, SECURITY_FIX_001)
 *
 * $Header: /vobs/my_project/include/utils.h@@/main/4  2024-05-20.11:30:00  mary.jones  $
 */

#ifndef UTILS_H
#define UTILS_H

/* --- version /main/1: bad include path (@@-extended, corner case) -------- */
/*
 * NOTE: The line below is an example of what ClearCase sometimes stores
 * when a developer accidentally commits with a version-extended path.
 * The migration tool rewrites this to a normal #include.
 */
#include "types.h@@/main/3"

/* Corrected form (what it should be after migration): */
/* #include "types.h" */

/* --- version /main/1 ---------------------------------------------------- */
char *str_copy(char *dst, const char *src, uint32_t max_len);
int   str_compare(const char *a, const char *b);
int   str_length(const char *s);

/* --- version /main/2 ---------------------------------------------------- */
char *str_trim(char *s);
int   str_split(char *s, char delim, char **parts, int max_parts);

/* --- version /main/3: circular buffer ------------------------------------ */
typedef struct {
    uint8_t  *buf;
    uint32_t  capacity;
    uint32_t  head;
    uint32_t  tail;
    uint32_t  count;
} circ_buf_t;

status_t circ_buf_init(circ_buf_t *cb, uint8_t *storage, uint32_t capacity);
status_t circ_buf_push(circ_buf_t *cb, uint8_t byte);
status_t circ_buf_pop(circ_buf_t *cb, uint8_t *out);
uint32_t circ_buf_available(const circ_buf_t *cb);
void     circ_buf_reset(circ_buf_t *cb);

/* --- version /main/4: safe memory functions (security fix) -------------- */
/*
 * Replaces raw memcpy calls that were found to be exploitable via
 * out-of-bounds writes when src_len was not validated by caller.
 */
status_t safe_memcpy(void *dst, uint32_t dst_size,
                     const void *src, uint32_t src_len);

#endif /* UTILS_H */
