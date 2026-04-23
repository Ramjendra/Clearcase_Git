/*
 * types.h -- common type definitions
 *
 * ClearCase version history:
 *   /main/0  : element created
 *   /main/1  : initial type definitions  (label: INITIAL_IMPORT)
 *   /main/2  : added error_t, status_t   (label: REL_1_0)
 *   /main/3  : added bool_t for ANSI C   (label: REL_2_0, REL_2_1)
 *
 * $Header: /vobs/my_project/include/types.h@@/main/3  2024-03-10.14:22:05  jsmith  $
 * $Id: types.h 3 2024-03-10 14:22:05Z jsmith $
 */

#ifndef TYPES_H
#define TYPES_H

/* --- version: /main/1 additions ----------------------------------------- */
typedef unsigned char  uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int   uint32_t;
typedef signed   char  int8_t;
typedef signed   short int16_t;
typedef signed   int   int32_t;

/* --- version: /main/2 additions ----------------------------------------- */
typedef int  error_t;
typedef int  status_t;

#define STATUS_OK       (0)
#define STATUS_ERROR   (-1)
#define STATUS_TIMEOUT (-2)
#define STATUS_NOMEM   (-3)

/* --- version: /main/3 additions ----------------------------------------- */
#ifndef __cplusplus
  typedef enum { false = 0, true = 1 } bool_t;
#else
  typedef bool bool_t;
#endif

/* max string buffer size used across the project */
#define MAX_BUF_SIZE  (256u)
#define MAX_PATH_LEN  (512u)

#endif /* TYPES_H */
