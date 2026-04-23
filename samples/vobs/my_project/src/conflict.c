/*
 * conflict.c  --  data processing module
 *
 * VERSION: /main/rel2_bugfix/2  (UNRESOLVED MERGE CONFLICT — corner case)
 *
 * This file was checked in to ClearCase with an unresolved merge conflict
 * between branch /main/rel2_bugfix and branch /main/rel3_feature.
 * The migration tool detects and flags the markers below.
 *
 * $Header: /vobs/my_project/src/conflict.c@@/main/rel2_bugfix/2  2024-02-10.09:00:00  jsmith  $
 */

#include <stdio.h>
#include <string.h>
#include "config.h"
#include "utils.h"

/*
 * CORNER CASE: ClearCase merge-conflict markers.
 * These look different from Git conflict markers — ClearCase uses 8 chars.
 *
 * <<<<<<< /main/rel2_bugfix/2 CHECKEDOUT
 *   version from rel2_bugfix branch
 * ======== (the separator)
 *   version from rel3_feature branch
 * >>>>>>> /main/rel3_feature/2
 *
 * Both versions are shown below exactly as ClearCase stored them.
 */

int process_data(const uint8_t *buf, uint32_t len, uint8_t *out)
{
<<<<<<< /main/rel2_bugfix/2 CHECKEDOUT
    /* rel2_bugfix: conservative bounds check — reject zero-length input */
    if (!buf || len == 0 || !out) return STATUS_ERROR;
    return safe_memcpy(out, len, buf, len);
========
    /* rel3_feature: allow zero-length pass-through for pipeline compatibility */
    if (!buf || !out) return STATUS_ERROR;
    if (len == 0) return STATUS_OK;
    return safe_memcpy(out, len, buf, len);
>>>>>>> /main/rel3_feature/2
}

/* The function below was unaffected by the merge and is clean */
int validate_checksum(const uint8_t *buf, uint32_t len, uint8_t expected)
{
    uint8_t  sum = 0;
    uint32_t i;
    for (i = 0; i < len; i++) sum ^= buf[i];
    return (sum == expected) ? STATUS_OK : STATUS_ERROR;
}
