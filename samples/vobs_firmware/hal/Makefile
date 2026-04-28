# $Header: /vobs/hal/Makefile@@/main/4 $
CLEARCASE_ROOT ?= /view/fw_migration_view
VOBROOT        := $(CLEARCASE_ROOT)/vobs

CXX      := g++
CXXFLAGS := -std=c++17 -Wall -fPIC
INCLUDES := -I$(VOBROOT)/hal/include -I$(VOBROOT)/shared_libs/include

SRCS := src/hal.cpp
OBJS := $(SRCS:.cpp=.o)
LIB  := libhal.a

.PHONY: all clean
all: $(LIB)
$(LIB): $(OBJS)
	ar rcs $@ $^
%.o: %.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@
clean:
	rm -f $(OBJS) $(LIB)
