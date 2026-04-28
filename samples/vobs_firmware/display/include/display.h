/* $Header: /vobs/display/include/display.h@@/main/3 $ */
#ifndef DISPLAY_H
#define DISPLAY_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include "/view/fw_migration_view/vobs/drivers/spi/include/spi_driver.h"
namespace fw { namespace display {
struct Rect { u16 x, y, w, h; };
struct Color { u8 r, g, b; };
class Display {
public:
    explicit Display(drivers::SpiDriver* spi);
    Status init(u16 width, u16 height);
    Status clear(Color bg);
    Status drawRect(const Rect& r, Color c);
    Status drawText(u16 x, u16 y, const char* text, Color c);
    Status flush();
    u16 width()  const { return m_w; }
    u16 height() const { return m_h; }
private:
    drivers::SpiDriver* m_spi;
    u16 m_w{0}, m_h{0};
};
}} // namespace fw::display
#endif
