#include "anomaly_detector.h"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const std::string& message)
{
    if (!condition)
    {
        throw std::runtime_error("断言失败：" + message);
    }
}

std::string readText(const std::string& path)
{
    std::ifstream stream(path.c_str());
    if (!stream)
    {
        throw std::runtime_error("无法读取配置：" + path);
    }
    std::ostringstream content;
    content << stream.rdbuf();
    return content.str();
}

void writeText(const std::string& path, const std::string& content)
{
    std::ofstream stream(path.c_str());
    if (!stream)
    {
        throw std::runtime_error("无法创建测试配置：" + path);
    }
    stream << content;
    if (!stream)
    {
        throw std::runtime_error("写入测试配置失败：" + path);
    }
}

std::string replaceValue(const std::string& content,
                         const std::string& key,
                         const std::string& value)
{
    std::istringstream input(content);
    std::ostringstream output;
    const std::string prefix = key + "=";
    std::string line;
    bool replaced = false;
    while (std::getline(input, line))
    {
        if (line.compare(0, prefix.size(), prefix) == 0)
        {
            line = prefix + value;
            replaced = true;
        }
        output << line << "\n";
    }
    if (!replaced)
    {
        throw std::runtime_error("测试配置缺少字段：" + key);
    }
    return output.str();
}

template <typename Function>
void expectInvalidArgument(Function function, const std::string& label)
{
    bool caught = false;
    try
    {
        function();
    }
    catch (const std::invalid_argument&)
    {
        caught = true;
    }
    catch (const std::exception& exception)
    {
        throw std::runtime_error(
            label + " 抛出了错误类型：" + exception.what());
    }
    require(caught, label + " 未抛出 std::invalid_argument");
}

template <typename Function>
void expectRuntimeError(Function function, const std::string& label)
{
    bool caught = false;
    try
    {
        function();
    }
    catch (const std::runtime_error&)
    {
        caught = true;
    }
    catch (const std::exception& exception)
    {
        throw std::runtime_error(
            label + " 抛出了错误类型：" + exception.what());
    }
    require(caught, label + " 未抛出 std::runtime_error");
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 5)
    {
        std::cerr << "用法: anomaly_detector_error_test "
                     "<param> <bin> <config> <scratch_dir>\n";
        return 2;
    }

    const std::string param_path = argv[1];
    const std::string bin_path = argv[2];
    const std::string config_path = argv[3];
    const std::string scratch_dir = argv[4];
    const std::string missing_fields_path =
        scratch_dir + "/missing_fields.conf";
    const std::string malformed_path =
        scratch_dir + "/malformed.conf";
    const std::string bad_threshold_path =
        scratch_dir + "/bad_threshold.conf";

    try
    {
        const std::string valid_config = readText(config_path);
        writeText(
            missing_fields_path,
            "window_size=60\nchannels=8\nthreads=1\n");
        writeText(malformed_path, "not_a_key_value_pair\n");
        writeText(
            bad_threshold_path,
            replaceValue(valid_config, "threshold_probability", "1.0"));

        std::vector<float> window(60 * 8, 0.0f);
        edge_ai::AnomalyDetector detector;
        std::string error;

        require(!detector.isLoaded(), "新实例不应处于已加载状态");
        expectRuntimeError(
            [&detector, &window]() {
                detector.score(window);
            },
            "未加载模型推理");

        require(
            !detector.load(
                param_path,
                bin_path,
                scratch_dir + "/missing.conf",
                &error),
            "缺失配置文件应加载失败");
        require(!error.empty(), "缺失配置文件应返回错误信息");

        require(
            !detector.load(
                scratch_dir + "/missing.param",
                bin_path,
                config_path,
                &error),
            "缺失模型文件应加载失败");
        require(!detector.isLoaded(), "模型加载失败后不应标记为已加载");

        require(
            !detector.load(
                param_path,
                bin_path,
                malformed_path,
                &error),
            "格式错误的配置应加载失败");
        require(
            !detector.load(
                param_path,
                bin_path,
                missing_fields_path,
                &error),
            "缺少必要字段的配置应加载失败");
        require(
            !detector.load(
                param_path,
                bin_path,
                bad_threshold_path,
                &error),
            "越界阈值应加载失败");

        require(
            detector.load(param_path, bin_path, config_path, &error),
            "有效配置应加载成功：" + error);
        require(detector.isLoaded(), "加载成功后 isLoaded 应为 true");
        require(detector.windowSize() == 60, "窗口长度应为 60");
        require(detector.channelCount() == 8, "通道数应为 8");
        require(
            detector.thresholdProbability() > 0.0f &&
                detector.thresholdProbability() < 1.0f,
            "概率阈值应位于 (0, 1)");

        const float probability = detector.score(window);
        require(std::isfinite(probability), "正常输入应输出有限概率");
        require(
            probability >= 0.0f && probability <= 1.0f,
            "正常输入概率应位于 [0, 1]");
        require(
            detector.isAnomaly(detector.thresholdProbability()),
            "阈值本身应判定为异常");

        expectInvalidArgument(
            [&detector, &window]() {
                std::vector<float> invalid(window.begin(), window.end() - 1);
                detector.score(invalid);
            },
            "错误窗口长度");

        window[0] = std::numeric_limits<float>::quiet_NaN();
        expectInvalidArgument(
            [&detector, &window]() {
                detector.score(window);
            },
            "NaN 输入");

        window[0] = std::numeric_limits<float>::infinity();
        expectInvalidArgument(
            [&detector, &window]() {
                detector.score(window);
            },
            "无穷输入");

        window[0] = 0.0f;
        require(
            !detector.load(param_path, bin_path, malformed_path, &error),
            "重复加载坏配置应失败");
        require(!detector.isLoaded(), "重复加载失败后应清空加载状态");
        require(
            detector.load(param_path, bin_path, config_path, &error),
            "失败后应能重新加载有效模型");
        require(
            std::isfinite(detector.score(window)),
            "重新加载后应能正常推理");

        std::remove(missing_fields_path.c_str());
        std::remove(malformed_path.c_str());
        std::remove(bad_threshold_path.c_str());
    }
    catch (const std::exception& exception)
    {
        std::cerr << exception.what() << "\n";
        return 1;
    }

    std::cout << "C++ AnomalyDetector 异常路径验收通过\n";
    return 0;
}
