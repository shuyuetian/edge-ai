#include "anomaly_detector.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <sys/resource.h>

namespace {

bool readFloatFile(const std::string& path, std::vector<float>& values)
{
    std::ifstream stream(path.c_str(), std::ios::binary | std::ios::ate);
    if (!stream)
    {
        return false;
    }
    const std::streamsize bytes = stream.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamsize>(sizeof(float)) != 0)
    {
        return false;
    }
    stream.seekg(0, std::ios::beg);
    values.resize(static_cast<std::size_t>(bytes) / sizeof(float));
    return static_cast<bool>(
        stream.read(reinterpret_cast<char*>(values.data()), bytes));
}

void sortAndCalculatePercentile(std::vector<double>& values,
                                const double percentile,
                                double& result)
{
    const std::size_t rank = static_cast<std::size_t>(
        std::ceil(percentile * static_cast<double>(values.size())));
    const std::size_t index = rank > 0 ? rank - 1 : 0;
    std::nth_element(values.begin(), values.begin() + index, values.end());
    result = values[index];
}

double mean(const std::vector<double>& values)
{
    double total = 0.0;
    for (std::size_t i = 0; i < values.size(); ++i)
    {
        total += values[i];
    }
    return total / static_cast<double>(values.size());
}

long peakRssKib()
{
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage) != 0)
    {
        return -1;
    }
    return usage.ru_maxrss;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 8)
    {
        std::cerr << "用法: anomaly_detector_benchmark "
                     "<param> <bin> <config> <raw_input.f32> "
                     "<sample_count> <warmup> <iterations>\n";
        return 2;
    }

    const std::string param_path = argv[1];
    const std::string bin_path = argv[2];
    const std::string config_path = argv[3];
    const std::string input_path = argv[4];
    const int sample_count = std::atoi(argv[5]);
    const int warmup = std::atoi(argv[6]);
    const int iterations = std::atoi(argv[7]);
    if (sample_count <= 0 || warmup < 0 || iterations <= 0)
    {
        std::cerr << "sample_count 和 iterations 必须大于 0，warmup 不得小于 0\n";
        return 2;
    }

    std::vector<float> raw_input;
    if (!readFloatFile(input_path, raw_input))
    {
        std::cerr << "输入夹具读取失败：" << input_path << "\n";
        return 2;
    }

    edge_ai::AnomalyDetector detector;
    std::string error;
    if (!detector.load(param_path, bin_path, config_path, &error))
    {
        std::cerr << error << "\n";
        return 1;
    }

    const std::size_t values_per_sample =
        static_cast<std::size_t>(detector.windowSize()) *
        static_cast<std::size_t>(detector.channelCount());
    if (raw_input.size() !=
        values_per_sample * static_cast<std::size_t>(sample_count))
    {
        std::cerr << "输入夹具元素数量与 sample_count 不一致\n";
        return 1;
    }

    volatile float checksum = 0.0f;
    try
    {
        for (int i = 0; i < warmup; ++i)
        {
            const std::size_t sample_index =
                static_cast<std::size_t>(i % sample_count);
            checksum += detector.score(
                raw_input.data() + sample_index * values_per_sample,
                values_per_sample);
        }

        std::vector<double> latencies_ms(static_cast<std::size_t>(iterations));
        for (int i = 0; i < iterations; ++i)
        {
            const std::size_t sample_index =
                static_cast<std::size_t>(i % sample_count);
            const std::chrono::steady_clock::time_point begin =
                std::chrono::steady_clock::now();
            const float probability = detector.score(
                raw_input.data() + sample_index * values_per_sample,
                values_per_sample);
            const std::chrono::steady_clock::time_point end =
                std::chrono::steady_clock::now();
            if (!std::isfinite(probability))
            {
                throw std::runtime_error("模型输出不是有限值");
            }
            checksum += probability;
            latencies_ms[static_cast<std::size_t>(i)] =
                std::chrono::duration<double, std::milli>(end - begin).count();
        }

        double p50_ms = 0.0;
        double p95_ms = 0.0;
        double p99_ms = 0.0;
        sortAndCalculatePercentile(latencies_ms, 0.50, p50_ms);
        sortAndCalculatePercentile(latencies_ms, 0.95, p95_ms);
        sortAndCalculatePercentile(latencies_ms, 0.99, p99_ms);
        const std::pair<std::vector<double>::iterator,
                        std::vector<double>::iterator> minmax =
            std::minmax_element(latencies_ms.begin(), latencies_ms.end());

        std::cout << std::fixed << std::setprecision(6);
        std::cout << "samples=" << sample_count << "\n";
        std::cout << "window=" << detector.windowSize()
                  << " channels=" << detector.channelCount() << "\n";
        std::cout << "warmup=" << warmup << " iterations=" << iterations << "\n";
        std::cout << "mean_ms=" << mean(latencies_ms) << "\n";
        std::cout << "p50_ms=" << p50_ms << "\n";
        std::cout << "p95_ms=" << p95_ms << "\n";
        std::cout << "p99_ms=" << p99_ms << "\n";
        std::cout << "min_ms=" << *minmax.first << "\n";
        std::cout << "max_ms=" << *minmax.second << "\n";
        std::cout << "peak_rss_kib=" << peakRssKib() << "\n";
        std::cout << "checksum=" << std::setprecision(9) << checksum << "\n";
    }
    catch (const std::exception& exception)
    {
        std::cerr << "基准运行失败：" << exception.what() << "\n";
        return 1;
    }
    return 0;
}
