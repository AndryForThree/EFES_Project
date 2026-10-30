cmake_minimum_required(VERSION 3.22)

#
# This file is generated only once,
# and is not re-generated if converter is called multiple times.
#
# User is free to modify the file as much as necessary
#

# Setup compiler settings
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)


# Define the build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Debug")
endif()

# Set the project name
set(CMAKE_PROJECT_NAME EFES_FW_HumanSide)

# Enable compile command to ease indexing with e.g. clangd
set(CMAKE_EXPORT_COMPILE_COMMANDS TRUE)

# Core project settings
project(${CMAKE_PROJECT_NAME})
message("Build type: " ${CMAKE_BUILD_TYPE})

# Enable CMake support for ASM and C languages
enable_language(C ASM)

# Create an executable object type
add_executable(${CMAKE_PROJECT_NAME})

# Add STM32CubeMX generated sources
add_subdirectory(cmake/stm32cubemx)

# Link directories setup
target_link_directories(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined library search paths
)

# Add sources to executable
target_sources(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user sources here
	customLibs/Communication/Communication.c
	customLibs/App/App.c
	customLibs/BUTTON/button.c
    customLibs/ST7789/st7789.c
    customLibs/ST7789/st7789_graphics.c
    customLibs/ST7789/st7789_transport.c
    customLibs/ST7789/Fonts/fonts_generated.c
    customLibs/ST7789/Assets/assets_generated.c
    customLibs/UI/UI_module.c
	customLibs/UI/UI_common.c
    customLibs/UI/UI_page_home/UI_home.c
    customLibs/UI/UI_page_sensor/UI_sensor.c
    customLibs/UI/UI_page_steering/UI_steering.c
	customLibs/UI/UI_page_settings/UI_settings.c
)

# Keep Debug optimization here: CubeMX regenerates the toolchain file.
# Target options follow the toolchain flags, so -Og overrides its -O0.
target_compile_options(${CMAKE_PROJECT_NAME} PRIVATE
    $<$<CONFIG:Debug>:-Og>
)

# Add include paths
target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined include paths
    customLibs/ST7789
    customLibs/UI
	customLibs/UI/UI_page_home
	customLibs/UI/UI_page_sensor
	customLibs/UI/UI_page_steering
	customLibs/UI/UI_page_settings
	customLibs/App
	customLibs/BUTTON
)

# Add project symbols (macros)
target_compile_definitions(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined symbols
)

# Remove wrong libob.a library dependency when using cpp files
list(REMOVE_ITEM CMAKE_C_IMPLICIT_LINK_LIBRARIES ob)

# Add linked libraries
target_link_libraries(${CMAKE_PROJECT_NAME}
    stm32cubemx
    m

    # Add user defined libraries
)
