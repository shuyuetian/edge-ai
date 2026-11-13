#include "anomaly_detector.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

template <typename T>
bool readBinary(const std::string& path, std::vector<T>& values)
{
    std::ifstream stream(path.c_str(), std::ios::binary | std::ios::ate);
    if (!stream)
    {
        return false;
    }
    const std::streamsize bytes = stream.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamsize>(sizeof(T)) != 0)
    {
        return false;
    }
    stream.seekg(0, std::ios::beg);
    values.resize(static_cast<std::size_t>(bytes) / sizeof(T));
    return static_cast<bool>(
        stream.read(reinterpret_cast<char*>(values.data()), bytes));
}

struct Metrics
{
    double precision;
    double recall;
    double f1;
    int true_negative;
    int false_positive;
    int false_negative;
    int true_positive;
};

Metrics calculateMetrics(const std::vector<signed char>& labels,
                         const std::vector<float>& probabilities,
                         float threshold)
{
    Metrics metrics = {0.0, 0.0, 0.0, 0, 0, 0, 0};
    for (std::size_t i = 0; i < labels.size(); ++i)
    {
        const bool predicted = probabilities[i] >= threshold;
        if (labels[i] == 0 && !predicted) ++metrics.true_negative;
        if (labels[i] == 0 && predicted) ++metrics.false_positive;
        if (labels[i] == 1 && !predicted) ++metrics.false_negative;
        if (labels[i] == 1 && predicted) ++metrics.true_positive;
    }
    metrics.precision = static_cast<double>(metrics.true_positive) /
        std::max(metrics.true_positive + metrics.false_positive, 1);
    metrics.recall = static_cast<double>(metrics.true_positive) /
        std::max(metrics.true_positive + metrics.false_negative, 1);
    metrics.f1 = metrics.precision + metrics.recall > 0.0
        ? 2.0 * metrics.precision * metrics.recall /
          (metrics.precision + metrics.recall)
        : 0.0;
    return metrics;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 8)
    {
        std::cerr << "用法: anomaly_detector_test <param> <bin> <config> "
                     "<raw_input.f32> <expected_probability.f32> "
                     "<labels.i8> <count>\n";
        return 2;
    }

    const std::string param_path = argv[1];
    const std::string bin_path = argv[2];
    const std::string config_path = argv[3];
    const int count = std::atoi(argv[7]);
    if (count <= 0)
    {
        std::cerr << "count 必须大于 0\n";
        return 2;
    }

    std::vector<float> raw_input;
    std::vector<float> expected_probability;
    std::vector<signed char> labels;
    if (!readBinary(argv[4], raw_input) ||
        !readBinary(argv[5], expected_probability) ||
        !readBinary(argv[6], labels))
    {
        std::cerr << "夹具文件读取失败\n";
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
    if (raw_input.size() != values_per_sample * static_cast<std::size_t>(count) ||
        expected_probability.size() != static_cast<std::size_t>(count) ||
        labels.size() != static_cast<std::size_t>(count))
    {
        std::cerr << "夹具元素数量不一致\n";
        return 1;
    }

    std::vector<float> actual_probability;
    actual_probability.reserve(static_cast<std::size_t>(count));
    double max_probability_error = 0.0;
    for (int index = 0; index < count; ++index)
    {
        const float probability = detector.score(
            raw_input.data() + index * values_per_sample,
            values_per_sample);
        if (!std::isfinite(probability) || probability < 0.0f || probability > 1.0f)
        {
            std::cerr << "第 " << index << " 个窗口输出概率非法\n";
            return 1;
        }
        actual_probability.push_back(probability);
        max_probability_error = std::max(
            max_probability_error,
            std::fabs(static_cast<double>(probability) -
                      static_cast<double>(expected_probability[index])));
    }

    const Metrics expected_metrics = calculateMetrics(
        labels, expected_probability, detector.thresholdProbability());
    const Metrics actual_metrics = calculateMetrics(
        labels, actual_probability, detector.thresholdProbability());

    int decision_differences = 0;
    for (int index = 0; index < count; ++index)
    {
        const bool expected =
            expected_probability[index] >= detector.thresholdProbability();
        const bool actual =
            actual_probability[index] >= detector.thresholdProbability();
        if (expected != actual)
        {
            ++decision_differences;
        }
    }
    const double decision_agreement =
        1.0 - static_cast<double>(decision_differences) / count;
    const double f1_drop = expected_metrics.f1 - actual_metrics.f1;

    bool rejected_bad_shape = false;
    try
    {
        std::vector<float> invalid(values_per_sample - 1, 0.0f);
        detector.score(invalid);
    }
    catch (const std::invalid_argument&)
    {
        rejected_bad_shape = true;
    }

    std::cout << std::fixed << std::setprecision(6);
    std::cout << "samples=" << count << "\n";
    std::cout << "window=" << detector.windowSize()
              << " channels=" << detector.channelCount() << "\n";
    std::cout << "threshold_probability=" << detector.thresholdProbability() << "\n";
    std::cout << "max_probability_error=" << max_probability_error << "\n";
    std::cout << "decision_differences=" << decision_differences << "\n";
    std::cout << "decision_agreement=" << decision_agreement << "\n";
    std::cout << "f1_drop=" << f1_drop << "\n";
    std::cout << "expected_precision=" << expected_metrics.precision
              << " expected_recall=" << expected_metrics.recall
              << " expected_f1=" << expected_metrics.f1 << "\n";
    std::cout << "actual_precision=" << actual_metrics.precision
              << " actual_recall=" << actual_metrics.recall
              << " actual_f1=" << actual_metrics.f1 << "\n";
    std::cout << "invalid_shape_rejected="
              << (rejected_bad_shape ? "true" : "false") << "\n";

    if (!rejected_bad_shape || decision_agreement < 0.99 || f1_drop > 0.01)
    {
        std::cerr << "C++ AnomalyDetector 验收失败\n";
        return 1;
    }
    std::cout << "C++ AnomalyDetector 验收通过\n";
    return 0;
}
