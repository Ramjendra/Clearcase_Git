/*
 * $Id: logger.cpp 3.4 2024/03/10 jsmith $
 * Firmware logger — singleton implementation.
 */
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
#include <cstdio>
#include <cstdarg>

namespace fw {
namespace log {

Logger& Logger::instance() {
    static Logger inst;
    return inst;
}

void Logger::setLevel(Level level) {
    m_level = level;
}

void Logger::log(Level level, const char* module, const char* fmt, ...) {
    if (level < m_level) return;
    const char* labels[] = {"DBG", "INF", "WRN", "ERR", "FAT"};
    fprintf(stderr, "[%s][%s] ", labels[static_cast<int>(level)], module);
    va_list args;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);
    fprintf(stderr, "\n");
}

} // namespace log
} // namespace fw
