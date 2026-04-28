/*
 * $Header: /vobs/firmware_core/include/firmware.h@@/main/rel3/8 2024/04/01 jsmith $
 * $Revision: 3.8 $
 * Main firmware orchestration header.
 * Includes all subsystems via ClearCase view paths.
 */
#ifndef FIRMWARE_H
#define FIRMWARE_H

#include "/view/fw_migration_view/vobs/platform/include/platform.h@@/main/4"
#include "/view/fw_migration_view/vobs/network/include/network.h@@/main/5"
#include "/view/fw_migration_view/vobs/storage/include/storage.h@@/main/rel3/3"
#include "/view/fw_migration_view/vobs/security/include/security.h@@/main/rel2_bugfix/4"
#include "/view/fw_migration_view/vobs/display/include/display.h@@/main/3"
#include "/view/fw_migration_view/vobs/audio/include/audio.h@@/main/2"
#include "/view/fw_migration_view/vobs/power/include/power.h@@/main/rel2_bugfix/3"
#include "/view/fw_migration_view/vobs/bootloader/include/bootloader.h@@/main/rel3/5"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h@@/main/rel3/4"

namespace fw {

class Firmware {
public:
    Status init();
    Status run();
    Status shutdown();

private:
    Status initSubsystems();
    Status runMainLoop();

    platform::PlatformConfig m_platCfg{
        120'000'000, 512*1024, 16*1024*1024, "FW-DEV-BOARD-v2"
    };
};

} // namespace fw

#endif // FIRMWARE_H
