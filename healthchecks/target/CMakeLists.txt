cmake_minimum_required(VERSION 3.16)
project(healthchecks_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Drogon REQUIRED)

add_executable(healthchecks main.cpp)
target_link_libraries(healthchecks PRIVATE Drogon::Drogon)
