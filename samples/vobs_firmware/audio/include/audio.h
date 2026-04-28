/* $Header: /vobs/audio/include/audio.h@@/main/2 $ */
#ifndef AUDIO_H
#define AUDIO_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/drivers/i2c/include/i2c_driver.h"
namespace fw { namespace audio {
struct AudioConfig { u32 sample_rate; u8 bit_depth; u8 channels; };
class AudioCodec {
public:
    explicit AudioCodec(drivers::I2cDriver* i2c);
    Status init(const AudioConfig& cfg);
    Status play(const u8* pcm_buf, u32 samples);
    Status record(u8* pcm_buf, u32 samples);
    Status setVolume(u8 vol_pct);
    Status mute(bool mute);
private:
    drivers::I2cDriver* m_i2c;
    AudioConfig m_cfg{};
};
}} // namespace fw::audio
#endif
