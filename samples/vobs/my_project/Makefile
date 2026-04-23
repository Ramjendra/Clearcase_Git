# Makefile  --  build system for my_project
#
# ClearCase version history:
#   /main/1  : initial Makefile             (label: INITIAL_IMPORT)
#   /main/2  : add debug/release targets    (label: REL_1_0)
#   /main/3  : add CLEARCASE_ROOT paths     (label: REL_2_0)  ← corner case
#   /main/4  : remove CC paths (fixed)      (label: REL_3_0)
#
# CORNER CASES in this file (version /main/3 — the problematic one):
#   1. $(CLEARCASE_ROOT) macro used as a path prefix
#   2. $(CLEARCASE_VIEWROOT) used for header search
#   3. Hard-coded /view/<viewname>/vobs/ path in INCLUDES
#
# The migration tool rewrites these to $(REPO_ROOT).
#
# $Header: /vobs/my_project/Makefile@@/main/3  2024-01-20.14:05:00  mary.jones  $

CC      = gcc
CFLAGS  = -Wall -Wextra -std=c99 -pedantic
LDFLAGS = -lpthread

# ---- CORNER CASE: CLEARCASE_ROOT used as a sysroot path ------------------
# Original (broken after migration):
#   SYSROOT  = $(CLEARCASE_ROOT)/vobs/my_project
#   INCLUDES = -I$(CLEARCASE_VIEWROOT)/vobs/my_project/include
#   LIBPATH  = /view/mary_dev_view/vobs/my_project/lib
#
# Migration tool rewrites to:
SYSROOT  = $(REPO_ROOT)/vobs/my_project
INCLUDES = -I$(REPO_ROOT)/vobs/my_project/include
LIBPATH  = $(REPO_ROOT)/vobs/my_project/lib
# -------------------------------------------------------------------------

SRCDIR  = src
INCDIR  = include
OBJDIR  = obj
BINDIR  = bin

SRCS    = $(SRCDIR)/main.c     \
          $(SRCDIR)/utils.c    \
          $(SRCDIR)/parser.c   \
          $(SRCDIR)/legacy.c

OBJS    = $(patsubst $(SRCDIR)/%.c, $(OBJDIR)/%.o, $(SRCS))
TARGET  = $(BINDIR)/my_project

# ---- version /main/1 targets --------------------------------------------

all: $(TARGET)

$(TARGET): $(OBJS) | $(BINDIR)
	$(CC) $(LDFLAGS) -o $@ $^

$(OBJDIR)/%.o: $(SRCDIR)/%.c | $(OBJDIR)
	$(CC) $(CFLAGS) $(INCLUDES) -c -o $@ $<

$(OBJDIR) $(BINDIR):
	mkdir -p $@

clean:
	rm -rf $(OBJDIR) $(BINDIR)

.PHONY: all clean

# ---- version /main/2: debug and release targets -------------------------

debug: CFLAGS += -g -DDEBUG -DLOGLEVEL=3
debug: $(TARGET)

release: CFLAGS += -O2 -DNDEBUG
release: $(TARGET)

# ---- dependency generation -----------------------------------------------
# Produces .d files so header changes trigger recompilation
DEPFLAGS = -MMD -MP
$(OBJDIR)/%.o: $(SRCDIR)/%.c | $(OBJDIR)
	$(CC) $(CFLAGS) $(INCLUDES) $(DEPFLAGS) -c -o $@ $<

-include $(OBJS:.o=.d)
