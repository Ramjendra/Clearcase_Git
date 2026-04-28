/* $Id: audio.cpp,v 2.0 2024/01/30 rmuller $ */
#include "audio/include/audio.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace audio {
AudioCodec::AudioCodec(drivers::I2cDriver* i2c) : m_i2c(i2c) {}
Status AudioCodec::init(const AudioConfig& cfg)        { m_cfg=cfg; FW_LOG_INFO("AUDIO","Init %luHz %dbit %dch",(unsigned long)cfg.sample_rate,cfg.bit_depth,cfg.channels); return Status::OK; }
Status AudioCodec::play(const u8* b, u32 s)            { (void)b;(void)s; return Status::OK; }
Status AudioCodec::record(u8* b, u32 s)                { (void)b;(void)s; return Status::OK; }
Status AudioCodec::setVolume(u8 v)                     { FW_LOG_DEBUG("AUDIO","Vol=%d%%",v); return Status::OK; }
Status AudioCodec::mute(bool m)                        { FW_LOG_DEBUG("AUDIO","Mute=%s",m?"ON":"OFF"); return Status::OK; }
}} // namespace fw::audio
