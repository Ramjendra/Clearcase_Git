/* $Id: power.cpp,v 3.2 2024/02/05 jsmith $ */
#include "power/include/power.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace power {
PowerManager::PowerManager(hal::IHal* hal) : m_hal(hal) {}
Status PowerManager::init()                           { FW_LOG_INFO("PWR","Init"); return Status::OK; }
Status PowerManager::setPowerMode(PowerMode m)        { const char* n[]={"ACTIVE","SLEEP","DEEP_SLEEP","HIB"}; FW_LOG_INFO("PWR","Mode->%s",n[(int)m]); m_mode=m; return Status::OK; }
BatteryStatus PowerManager::getBatteryStatus() const  { return {85, false, 3700}; }
Status PowerManager::enablePeripheral(u8 id, bool en) { FW_LOG_DEBUG("PWR","Periph %d -> %s",id,en?"ON":"OFF"); return Status::OK; }
Status PowerManager::registerWakeSource(u8 id)        { (void)id; return Status::OK; }
}} // namespace fw::power
