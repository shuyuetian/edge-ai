#include "anomaly_detector.h"
#include "sensor_stream.h"

#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

int parseStride(const char* text)
{
    errno = 0;
    char* end = NULL;
    const long value = std::strtol(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0' ||
        value <= 0 || value > 1000000)
    {
        throw std::invalid_argument("stride 必须是 1 到 1000000 的整数");
    }
    return static_cast<int>(value);
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 5 && argc != 6)
    {
        std::cerr << "用法: anomaly_detector_stream "
                     "<param> <bin> <config> <csv|-> [stride]\n";
        return 2;
    }

    try
    {
        const int stride = argc == 6 ? parseStride(argv[5]) : 10;
        edge_ai::AnomalyDetector detector;
        std::string error;
        if (!detector.load(argv[1], argv[2], argv[3], &error))
        {
            std::cerr << error << "\n";
            return 1;
        }

        std::ifstream file;
        std::istream* input = &std::cin;
        const std::string csv_path = argv[4];
        if (csv_path != "-")
        {
            file.open(csv_path.c_str());
            if (!file)
            {
                std::cerr << "无法打开 CSV：" << csv_path << "\n";
                return 1;
            }
            input = &file;
        }

        edge_ai::CsvSensorReader reader(
            *input, static_cast<std::size_t>(detector.channelCount()));
        edge_ai::SlidingWindowStream stream(
            detector.windowSize(), detector.channelCount(), stride);

        std::cout << "timestamp,unix_seconds,probability,is_anomaly\n";
        std::cout << std::fixed << std::setprecision(9);

        edge_ai::SensorRecord record;
        std::size_t input_rows = 0;
        std::size_t output_windows = 0;
        while (reader.read(record))
        {
            ++input_rows;
            std::vector<edge_ai::StreamWindow> windows;
            stream.push(
                record.timestamp_seconds,
                record.timestamp_text,
                record.sensor_values.data(),
                record.sensor_values.size(),
                &windows);
            for (std::size_t i = 0; i < windows.size(); ++i)
            {
                const float probability =
                    detector.score(windows[i].sensor_values);
                std::cout << windows[i].timestamp_text << ','
                          << windows[i].timestamp_seconds << ','
                          << probability << ','
                          << (detector.isAnomaly(probability) ? 1 : 0)
                          << '\n';
                std::cout.flush();
                ++output_windows;
            }
        }

        std::cerr << "delimiter=" << reader.delimiter()
                  << " input_rows=" << input_rows
                  << " windows=" << output_windows
                  << " segments=" << stream.segmentCount()
                  << " stride=" << stride << "\n";
        return 0;
    }
    catch (const std::exception& exception)
    {
        std::cerr << "流式推理失败：" << exception.what() << "\n";
        return 1;
    }
}
