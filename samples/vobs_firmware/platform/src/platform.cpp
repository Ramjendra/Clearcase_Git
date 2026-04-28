/* $Id: platform.cpp,v 4.1 2024/03/08 jsmith $ */
#include "platform/include/platform.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace platform {
static PlatformConfig g_cfg{};
Status platformInit(const PlatformConfig& cfg) {
    g_cfg = cfg;
    FW_LOG_INFO("PLAT","Board=%s CPU=%luMHz RAM=%luKB Flash=%luKB",
        cfg.board_name, (unsigned long)cfg.cpu_freq_hz/1000000,
        (unsigned long)cfg.ram_size/1024, (unsigned long)cfg.flash_size/1024);
    return hal::getHal()->init();
}
hal::IHal*             getPlatformHal()    { return hal::getHal(); }
const PlatformConfig&  getPlatformConfig() { return g_cfg; }
void platformReset()                       { FW_LOG_ERROR("PLAT","RESET"); }
void platformWatchdogKick()                {}
}} // namespace fw::platform
