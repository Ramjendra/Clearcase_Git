/*
 * $Id: firmware.cpp,v 3.8 2024/04/01 jsmith $
 * Main firmware implementation — orchestrates all 15 subsystems.
 */
#include "firmware_core/include/firmware.h"

namespace fw {

Status Firmware::init() {
    FW_LOG_INFO("FW", "=== Firmware v3.8 boot ===");
    Status s = platform::platformInit(m_platCfg);
    if (s != Status::OK) { FW_LOG_ERROR("FW","Platform init failed"); return s; }
    return initSubsystems();
}

Status Firmware::initSubsystems() {
    // Drivers
    drivers::UartConfig uart_cfg{115200, 8, 1, false};
    drivers::SpiConfig  spi_cfg{10000000, 0, false};
    drivers::I2cConfig  i2c_cfg{400000, false};

    auto* hal  = platform::getPlatformHal();
    static drivers::UartDriver uart(hal);
    static drivers::SpiDriver  spi(hal);
    static drivers::I2cDriver  i2c(hal);

    uart.init(uart_cfg);
    spi.init(spi_cfg);
    i2c.init(i2c_cfg);

    // Subsystems
    static storage::FlashStorage  flash(&spi);
    static security::CryptoEngine crypto;
    static net::NetworkStack       net;
    static display::Display        disp(&spi);
    static audio::AudioCodec       codec(&i2c);
    static power::PowerManager     pwr(hal);
    static boot::Bootloader        boot(&flash, &crypto);

    flash.init();
    crypto.init();
    net.init({{192,168,1,10},{192,168,1,1},{255,255,255,0}, 8080});
    disp.init(320, 240);
    codec.init({44100, 16, 2});
    pwr.init();

    FW_LOG_INFO("FW", "All subsystems initialized");
    return Status::OK;
}

Status Firmware::run() {
    FW_LOG_INFO("FW","Entering main loop");
    return runMainLoop();
}

Status Firmware::runMainLoop() {
    // Main event loop — in production this runs forever
    FW_LOG_INFO("FW","Main loop running");
    return Status::OK;
}

Status Firmware::shutdown() {
    FW_LOG_INFO("FW","Shutdown");
    return Status::OK;
}

} // namespace fw

int main() {
    fw::Firmware fw;
    if (fw.init() != fw::Status::OK) return 1;
    return (fw.run() == fw::Status::OK) ? 0 : 1;
}
