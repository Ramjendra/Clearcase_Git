/* $Id: display.cpp,v 3.1 2024/02/28 mary.jones $ */
#include "display/include/display.h"
#include "/view/fw_migration_view/vobs/shared_libs/include/logger.h"
namespace fw { namespace display {
Display::Display(drivers::SpiDriver* spi) : m_spi(spi) {}
Status Display::init(u16 w, u16 h)               { m_w=w; m_h=h; FW_LOG_INFO("DISP","Init %dx%d",w,h); return Status::OK; }
Status Display::clear(Color bg)                  { (void)bg; return Status::OK; }
Status Display::drawRect(const Rect& r, Color c) { (void)r;(void)c; return Status::OK; }
Status Display::drawText(u16 x, u16 y, const char* t, Color c) { (void)x;(void)y;(void)t;(void)c; return Status::OK; }
Status Display::flush()                          { return Status::OK; }
}} // namespace fw::display
