#ifndef PIZERO_BIKECOMPUTER_MIP_DISPLAY_HPP
#define PIZERO_BIKECOMPUTER_MIP_DISPLAY_HPP

// Select the implementation backend at build time.
// Exactly one backend macro must be defined by the extension build.
#if defined(MIP_DISPLAY_BACKEND_PIGPIO)
#include "mip_display_pigpio.hpp"
#elif defined(MIP_DISPLAY_BACKEND_SPIDEV)
#include "mip_display_spidev.hpp"
#else
#error "Define MIP_DISPLAY_BACKEND_PIGPIO or MIP_DISPLAY_BACKEND_SPIDEV"
#endif

#endif

