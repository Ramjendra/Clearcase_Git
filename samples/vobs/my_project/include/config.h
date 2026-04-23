/*
 * config.h -- compile-time configuration
 *
 * ClearCase version history:
 *   /main/1  : initial config              (label: INITIAL_IMPORT)
 *   /main/2  : added DEBUG/TRACE macros    (label: REL_1_0)
 *   /main/rel2_bugfix/1 : hotfix LOGLEVEL  (label: REL_1_0_PATCH1)
 *   /main/3  : merged rel2_bugfix, added WATCHDOG_TIMEOUT (label: REL_2_0)
 *
 * ---- CC keyword expanded (as ClearCase stores it) ----
 * $Header: /vobs/my_project/include/config.h@@/main/3  2024-04-01.09:15:00  build_svc  $
 * $Author: build_svc $
 * $Date: 2024/04/01 09:15:00 $
 * $Locker:  $
 * $Revision: 3 $
 * $Source: /vobs/my_project/include/config.h $
 * $State: Exp $
 * -------------------------------------------------------
 */

#ifndef CONFIG_H
#define CONFIG_H

#include "types.h"

/* --- version /main/1 ---------------------------------------------------- */
#define APP_NAME        "MyProject"
#define APP_VERSION     "0.0.1"

/* --- version /main/2 ---------------------------------------------------- */
#ifdef DEBUG
  #define DBG_PRINT(fmt, ...) fprintf(stderr, "[DBG] " fmt "\n", ##__VA_ARGS__)
  #define TRACE_ENTER(fn)     fprintf(stderr, "[TRACE] --> %s\n", fn)
  #define TRACE_EXIT(fn)      fprintf(stderr, "[TRACE] <-- %s\n", fn)
#else
  #define DBG_PRINT(fmt, ...)  /* nothing */
  #define TRACE_ENTER(fn)      /* nothing */
  #define TRACE_EXIT(fn)       /* nothing */
#endif

/* Log levels */
#define LOG_ERROR   (0)
#define LOG_WARN    (1)
#define LOG_INFO    (2)
#define LOG_DEBUG   (3)

/* --- version /main/rel2_bugfix/1 (merged to /main/3) -------------------- */
/*
 * LOGLEVEL was previously hard-coded to LOG_INFO.
 * Bug: debug builds were silently dropping error messages below LOG_WARN.
 * Fix: make configurable at compile time with safe default.
 */
#ifndef LOGLEVEL
  #define LOGLEVEL  LOG_WARN
#endif

/* --- version /main/3 ---------------------------------------------------- */
#define WATCHDOG_TIMEOUT_MS  (5000u)
#define HEARTBEAT_INTERVAL_MS (1000u)

#endif /* CONFIG_H */
