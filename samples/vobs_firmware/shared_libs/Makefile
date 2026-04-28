# $Header: /vobs/shared_libs/Makefile@@/main/5 $
# Shared libs — compiled first; all other VOBs link against this.

CLEARCASE_ROOT ?= /view/fw_migration_view
VOBROOT        := $(CLEARCASE_ROOT)/vobs

CXX      := g++
CXXFLAGS := -std=c++17 -Wall -fPIC
INCLUDES := -I$(VOBROOT)/shared_libs/include

SRCS := src/logger.cpp
OBJS := $(SRCS:.cpp=.o)
LIB  := libfw_shared.a

.PHONY: all clean

all: $(LIB)

$(LIB): $(OBJS)
	ar rcs $@ $^

%.o: %.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@

clean:
	rm -f $(OBJS) $(LIB)
