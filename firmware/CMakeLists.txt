cmake_minimum_required(VERSION 3.13)

include(pico-sdk/pico_sdk_init.cmake)

project(keyboard)

# initialize the Raspberry Pi Pico SDK
pico_sdk_init()

add_executable(picokeyboard)

target_sources(picokeyboard PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/src/main.c
        ${CMAKE_CURRENT_SOURCE_DIR}/src/usb_descriptors.c
)

# Example include
target_include_directories(picokeyboard PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(picokeyboard PUBLIC pico_stdlib tinyusb_device hardware_adc)

# for generating .uf2
pico_add_extra_outputs(picokeyboard)

