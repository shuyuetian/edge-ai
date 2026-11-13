cmake_minimum_required(VERSION 3.10)
project(edge_ai_inference CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(NCNN_SOURCE_DIR "" CACHE PATH "ncnn source directory")
set(NCNN_BUILD_DIR "" CACHE PATH "ncnn build directory containing generated headers")
set(NCNN_LIBRARY "" CACHE FILEPATH "built libncnn.a")
set(EDGE_AI_ARTIFACT_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/../train/artifacts"
    CACHE PATH
    "directory containing model and test artifacts")
option(EDGE_AI_BUILD_TESTS "Build inference integration tests" ON)
option(EDGE_AI_BUILD_BENCHMARKS "Build inference latency benchmarks" ON)
option(EDGE_AI_BUILD_STREAM_TOOL "Build CSV streaming detector" ON)
option(EDGE_AI_STATIC_RUNTIME "Statically link the C/C++ runtime and OpenMP" OFF)
option(EDGE_AI_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

if(EDGE_AI_ENABLE_SANITIZERS)
    if(EDGE_AI_STATIC_RUNTIME)
        message(FATAL_ERROR "Sanitizer builds cannot use EDGE_AI_STATIC_RUNTIME")
    endif()
    set(CMAKE_CXX_FLAGS
        "${CMAKE_CXX_FLAGS} -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -g")
    set(CMAKE_EXE_LINKER_FLAGS
        "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=address,undefined")
endif()

if(NOT EXISTS "${NCNN_SOURCE_DIR}/src/net.h")
    message(FATAL_ERROR "NCNN_SOURCE_DIR is invalid: ${NCNN_SOURCE_DIR}")
endif()
if(NOT EXISTS "${NCNN_BUILD_DIR}/src/platform.h")
    message(FATAL_ERROR "NCNN_BUILD_DIR is invalid: ${NCNN_BUILD_DIR}")
endif()
if(NOT EXISTS "${NCNN_LIBRARY}")
    message(FATAL_ERROR "NCNN_LIBRARY does not exist: ${NCNN_LIBRARY}")
endif()

find_package(Threads REQUIRED)
find_package(OpenMP REQUIRED)
enable_testing()

if(EDGE_AI_STATIC_RUNTIME)
    execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" -print-file-name=libgomp.a
        OUTPUT_VARIABLE GOMP_STATIC_LIBRARY
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(NOT EXISTS "${GOMP_STATIC_LIBRARY}")
        message(FATAL_ERROR "Static libgomp.a not found for ${CMAKE_CXX_COMPILER}")
    endif()
endif()

add_library(edge_ai_inference STATIC
    src/anomaly_detector.cpp
    src/sensor_stream.cpp
)
target_include_directories(edge_ai_inference
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
    PUBLIC
        "${NCNN_SOURCE_DIR}/src"
        "${NCNN_BUILD_DIR}/src"
)
if(EDGE_AI_STATIC_RUNTIME)
    target_link_libraries(edge_ai_inference
        PUBLIC
            "${NCNN_LIBRARY}"
            Threads::Threads
            "${GOMP_STATIC_LIBRARY}"
    )
else()
    target_link_libraries(edge_ai_inference
        PUBLIC
            "${NCNN_LIBRARY}"
            Threads::Threads
            OpenMP::OpenMP_CXX
    )
endif()
target_compile_options(edge_ai_inference PRIVATE -Wall -Wextra)

if(EDGE_AI_BUILD_TESTS)
    add_executable(anomaly_detector_test tests/anomaly_detector_test.cpp)
    target_link_libraries(anomaly_detector_test PRIVATE edge_ai_inference)
    target_compile_options(anomaly_detector_test PRIVATE -Wall -Wextra)

    add_executable(
        anomaly_detector_error_test
        tests/anomaly_detector_error_test.cpp
    )
    target_link_libraries(anomaly_detector_error_test PRIVATE edge_ai_inference)
    target_compile_options(anomaly_detector_error_test PRIVATE -Wall -Wextra)

    add_executable(sensor_stream_test tests/sensor_stream_test.cpp)
    target_link_libraries(sensor_stream_test PRIVATE edge_ai_inference)
    target_compile_options(sensor_stream_test PRIVATE -Wall -Wextra)

    if(EDGE_AI_STATIC_RUNTIME)
        set_property(TARGET anomaly_detector_test APPEND_STRING PROPERTY LINK_FLAGS " -static")
        set_property(
            TARGET anomaly_detector_error_test
            APPEND_STRING
            PROPERTY LINK_FLAGS " -static"
        )
        set_property(
            TARGET sensor_stream_test
            APPEND_STRING
            PROPERTY LINK_FLAGS " -static"
        )
    endif()

    if(NOT CMAKE_CROSSCOMPILING)
        add_test(
            NAME anomaly_detector_integration
            COMMAND anomaly_detector_test
                "${EDGE_AI_ARTIFACT_DIR}/anomaly_cnn_int8.param"
                "${EDGE_AI_ARTIFACT_DIR}/anomaly_cnn_int8.bin"
                "${CMAKE_CURRENT_SOURCE_DIR}/model_config.txt"
                "${EDGE_AI_ARTIFACT_DIR}/detector_fixture/raw_input.f32"
                "${EDGE_AI_ARTIFACT_DIR}/detector_fixture/expected_probability.f32"
                "${EDGE_AI_ARTIFACT_DIR}/detector_fixture/labels.i8"
                481
        )
        add_test(
            NAME anomaly_detector_error_paths
            COMMAND anomaly_detector_error_test
                "${EDGE_AI_ARTIFACT_DIR}/anomaly_cnn_int8.param"
                "${EDGE_AI_ARTIFACT_DIR}/anomaly_cnn_int8.bin"
                "${CMAKE_CURRENT_SOURCE_DIR}/model_config.txt"
                "${CMAKE_CURRENT_BINARY_DIR}"
        )
        add_test(NAME sensor_stream_logic COMMAND sensor_stream_test)
    endif()
endif()

if(EDGE_AI_BUILD_BENCHMARKS)
    add_executable(anomaly_detector_benchmark
        benchmark/anomaly_detector_benchmark.cpp
    )
    target_link_libraries(anomaly_detector_benchmark PRIVATE edge_ai_inference)
    target_compile_options(anomaly_detector_benchmark PRIVATE -Wall -Wextra)
    if(EDGE_AI_STATIC_RUNTIME)
        set_property(
            TARGET anomaly_detector_benchmark
            APPEND_STRING
            PROPERTY LINK_FLAGS " -static"
        )
    endif()
endif()

if(EDGE_AI_BUILD_STREAM_TOOL)
    add_executable(anomaly_detector_stream
        apps/anomaly_detector_stream.cpp
    )
    target_link_libraries(anomaly_detector_stream PRIVATE edge_ai_inference)
    target_compile_options(anomaly_detector_stream PRIVATE -Wall -Wextra)
    if(EDGE_AI_STATIC_RUNTIME)
        set_property(
            TARGET anomaly_detector_stream
            APPEND_STRING
            PROPERTY LINK_FLAGS " -static"
        )
    endif()
endif()
