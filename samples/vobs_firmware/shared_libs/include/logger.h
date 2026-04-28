/*
 * $Header: /vobs/shared_libs/include/logger.h@@/main/rel3/4 2024/03/10 09:15:00 jsmith $
 * $Revision: 3.4 $
 */
#ifndef SHARED_LIBS_LOGGER_H
#define SHARED_LIBS_LOGGER_H

#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h@@/main/3"

namespace fw {
namespace log {

enum class Level { DEBUG, INFO, WARN, ERROR, FATAL };

class Logger {
public:
    static Logger& instance();
    void log(Level level, const char* module, const char* fmt, ...);
    void setLevel(Level level);
private:
    Logger() = default;
    Level m_level{Level::INFO};
};

#define FW_LOG_INFO(mod, fmt, ...)  fw::log::Logger::instance().log(fw::log::Level::INFO,  mod, fmt, ##__VA_ARGS__)
#define FW_LOG_ERROR(mod, fmt, ...) fw::log::Logger::instance().log(fw::log::Level::ERROR, mod, fmt, ##__VA_ARGS__)
#define FW_LOG_DEBUG(mod, fmt, ...) fw::log::Logger::instance().log(fw::log::Level::DEBUG, mod, fmt, ##__VA_ARGS__)

} // namespace log
} // namespace fw

#endif // SHARED_LIBS_LOGGER_H
