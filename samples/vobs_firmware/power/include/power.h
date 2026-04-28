/* $Header: /vobs/power/include/power.h@@/main/rel2_bugfix/3 $ */
#ifndef POWER_H
#define POWER_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/hal/include/hal.h"
namespace fw { namespace power {
enum class PowerMode { ACTIVE, SLEEP, DEEP_SLEEP, HIBERNATE };
struct BatteryStatus { u8 level_pct; bool charging; u32 voltage_mv; };
class PowerManager {
public:
    explicit PowerManager(hal::IHal* hal);
    Status init();
    Status setPowerMode(PowerMode mode);
    BatteryStatus getBatteryStatus() const;
    Status enablePeripheral(u8 periph_id, bool enable);
    Status registerWakeSource(u8 source_id);
private:
    hal::IHal* m_hal;
    PowerMode  m_mode{PowerMode::ACTIVE};
};
}} // namespace fw::power
#endif
