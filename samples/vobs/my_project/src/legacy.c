/*
 * legacy.c  --  legacy hardware abstraction layer (HAL)
 *
 * VERSION: /main/2   LABEL: REL_2_0
 *
 * ENCODING CORNER CASE:
 * This file is stored in ISO-8859-1 (Latin-1). It was written on a
 * Western European Windows workstation in 2009 and never re-encoded.
 * The special characters below are ISO-8859-1 byte values:
 *
 *   \xe9 = é  (e-acute)
 *   \xfc = ü  (u-umlaut)
 *   \xe0 = à  (a-grave)
 *   \xa9 = ©  (copyright)
 *   \xb5 = µ  (micro sign)
 *   \xb0 = °  (degree sign)
 *
 * Original author: René Müller, München
 * Copyright © 2009 Société Électronique
 *
 * The migration tool detects ISO-8859-1, converts to UTF-8, and records
 * this in logs/c_file_issues.md.
 *
 * $Header: /vobs/my_project/src/legacy.c@@/main/2  2024-01-10.08:30:00  rmuller  $
 */

#include <string.h>
#include "config.h"
#include "utils.h"

/*
 * HAL register map for µController XC2000
 * Operating range: -40°C to +85°C
 * Société Électronique part# SE-HAL-2024
 */

#define HAL_BASE_ADDR    0x40000000UL
#define HAL_REG_CTRL     (HAL_BASE_ADDR + 0x00)
#define HAL_REG_STATUS   (HAL_BASE_ADDR + 0x04)
#define HAL_REG_DATA     (HAL_BASE_ADDR + 0x08)
#define HAL_REG_IRQ_MASK (HAL_BASE_ADDR + 0x0C)

#define HAL_CTRL_ENABLE  (1u << 0)
#define HAL_CTRL_RESET   (1u << 1)
#define HAL_CTRL_IRQ_EN  (1u << 2)

typedef volatile uint32_t *reg_t;

static inline void reg_write(uint32_t addr, uint32_t val)
{
    *((reg_t)(uintptr_t)addr) = val;
}

static inline uint32_t reg_read(uint32_t addr)
{
    return *((reg_t)(uintptr_t)addr);
}

/* ---- public API -------------------------------------------------------- */

status_t hal_init(void)
{
    /* Assert reset, then deassert and enable — µs delay between steps */
    reg_write(HAL_REG_CTRL, HAL_CTRL_RESET);
    /* busy-wait ~10µs at 100 MHz → 1000 cycles */
    volatile int i;
    for (i = 0; i < 1000; i++) { /* nothing */ }
    reg_write(HAL_REG_CTRL, HAL_CTRL_ENABLE | HAL_CTRL_IRQ_EN);

    if (!(reg_read(HAL_REG_STATUS) & 0x01u)) {
        DBG_PRINT("HAL init failed: STATUS=0x%08X", reg_read(HAL_REG_STATUS));
        return STATUS_ERROR;
    }
    return STATUS_OK;
}

status_t hal_write(const uint8_t *data, uint32_t len)
{
    uint32_t i;
    if (!data || len == 0) return STATUS_ERROR;
    for (i = 0; i < len; i++) {
        /* Wait for TX-ready bit (bit 1) — max WATCHDOG_TIMEOUT_MS polls */
        uint32_t timeout = WATCHDOG_TIMEOUT_MS * 1000u;
        while (!(reg_read(HAL_REG_STATUS) & 0x02u)) {
            if (--timeout == 0) return STATUS_TIMEOUT;
        }
        reg_write(HAL_REG_DATA, data[i]);
    }
    return STATUS_OK;
}

status_t hal_read(uint8_t *buf, uint32_t len, uint32_t *actual)
{
    uint32_t i = 0;
    if (!buf || !actual) return STATUS_ERROR;
    *actual = 0;
    while (i < len && (reg_read(HAL_REG_STATUS) & 0x04u)) {
        buf[i++] = (uint8_t)(reg_read(HAL_REG_DATA) & 0xFFu);
    }
    *actual = i;
    return STATUS_OK;
}
