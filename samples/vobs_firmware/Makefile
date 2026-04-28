# =============================================================================
# $Header: /vobs/firmware_core/Makefile@@/main/rel3/12 2024/04/01 jsmith $
# Top-level shared compilation Makefile — builds all 15 VOBs in dependency order.
# =============================================================================
#
# SHARED COMPILATION: All VOBs share headers via CLEARCASE_ROOT/VOBROOT.
# After migration, replace CLEARCASE_ROOT with REPO_ROOT pointing to git root.

CLEARCASE_ROOT  ?= /view/fw_migration_view
VOBROOT         := $(CLEARCASE_ROOT)/vobs
CC_VOB_BASE     := $(CLEARCASE_ROOT)/vobs

CXX             := g++
CXXFLAGS        := -std=c++17 -Wall -Wextra -fPIC -O2
AR              := ar

# Shared include path — all VOBs are siblings under VOBROOT
SHARED_INCLUDES := \
    -I$(VOBROOT)/shared_libs/include   \
    -I$(VOBROOT)/hal/include           \
    -I$(VOBROOT)/drivers/uart/include  \
    -I$(VOBROOT)/drivers/spi/include   \
    -I$(VOBROOT)/drivers/i2c/include   \
    -I$(VOBROOT)/network/include       \
    -I$(VOBROOT)/storage/include       \
    -I$(VOBROOT)/security/include      \
    -I$(VOBROOT)/display/include       \
    -I$(VOBROOT)/audio/include         \
    -I$(VOBROOT)/power/include         \
    -I$(VOBROOT)/bootloader/include    \
    -I$(VOBROOT)/test_framework/include\
    -I$(VOBROOT)/platform/include      \
    -I$(VOBROOT)/firmware_core/include

# Build order: dependencies first
VOBS_IN_ORDER := \
    shared_libs        \
    hal                \
    drivers/uart       \
    drivers/spi        \
    drivers/i2c        \
    network            \
    storage            \
    security           \
    display            \
    audio              \
    power              \
    platform           \
    bootloader         \
    test_framework     \
    firmware_core

.PHONY: all clean $(VOBS_IN_ORDER)

all: $(VOBS_IN_ORDER)

$(VOBS_IN_ORDER):
	$(MAKE) -C $(VOBROOT)/$@ VOBROOT=$(VOBROOT) SHARED_INCLUDES="$(SHARED_INCLUDES)"

# Firmware core depends on all others
firmware_core: shared_libs hal drivers/uart drivers/spi drivers/i2c \
               network storage security display audio power platform \
               bootloader test_framework

clean:
	@for vob in $(VOBS_IN_ORDER); do \
	    $(MAKE) -C $(VOBROOT)/$$vob clean 2>/dev/null || true; \
	done

# Cross-VOB test target
test: all
	$(MAKE) -C $(VOBROOT)/test_framework run_tests VOBROOT=$(VOBROOT)
