cmake_minimum_required(VERSION 3.10)
project(healthchecks_cpp CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(healthchecks main.cpp)

if(WIN32)
  target_link_libraries(healthchecks PRIVATE ws2_32)
endif()
