/* $Header: /vobs/platform/include/platform.h@@/main/4 $ */
#ifndef PLATFORM_H
#define PLATFORM_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/hal/include/hal.h"
namespace fw { namespace platform {
struct PlatformConfig {
    u32 cpu_freq_hz;
    u32 ram_size;
    u32 flash_size;
    const char* board_name;
};
Status platformInit(const PlatformConfig& cfg);
hal::IHal* getPlatformHal();
const PlatformConfig& getPlatformConfig();
void platformReset();
void platformWatchdogKick();
}} // namespace fw::platform
#endif
