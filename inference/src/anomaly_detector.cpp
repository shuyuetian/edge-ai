#include "anomaly_detector.h"

#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace edge_ai {

namespace {

std::string trim(const std::string& value)
{
    const std::string whitespace = " \t\r\n";
    const std::string::size_type begin = value.find_first_not_of(whitespace);
    if (begin == std::string::npos)
    {
        return std::string();
    }
    const std::string::size_type end = value.find_last_not_of(whitespace);
    return value.substr(begin, end - begin + 1);
}

bool parseFloatList(const std::string& text, std::vector<float>& values)
{
    values.clear();
    std::istringstream stream(text);
    std::string item;
    while (std::getline(stream, item, ','))
    {
        std::istringstream item_stream(trim(item));
        float value = 0.0f;
        if (!(item_stream >> value))
        {
            return false;
        }
        values.push_back(value);
    }
    return !values.empty();
}

bool parseInteger(const std::string& text, int& value)
{
    std::istringstream stream(trim(text));
    return static_cast<bool>(stream >> value);
}

bool parseFloat(const std::string& text, float& value)
{
    std::istringstream stream(trim(text));
    return static_cast<bool>(stream >> value);
}

float sigmoid(float value)
{
    if (value >= 0.0f)
    {
        return 1.0f / (1.0f + std::exp(-value));
    }
    const float exponential = std::exp(value);
    return exponential / (1.0f + exponential);
}

void setError(std::string* error, const std::string& message)
{
    if (error)
    {
        *error = message;
    }
}

} // namespace

AnomalyDetector::AnomalyDetector()
    : loaded_(false),
      window_size_(60),
      channel_count_(8),
      threads_(1),
      threshold_probability_(0.5f),
      threshold_logit_(0.0f)
{
}

AnomalyDetector::~AnomalyDetector()
{
}

bool AnomalyDetector::load(const std::string& param_path,
                           const std::string& bin_path,
                           const std::string& config_path,
                           std::string* error)
{
    loaded_ = false;
    if (!parseConfig(config_path, error))
    {
        return false;
    }

    if (window_size_ != 60 || channel_count_ != 8)
    {
        setError(error, "当前模型只支持 60 秒窗口和 8 路输入");
        return false;
    }

    if (mean_.size() != static_cast<std::size_t>(channel_count_) ||
        stddev_.size() != static_cast<std::size_t>(channel_count_))
    {
        setError(error, "标准化参数数量与通道数不一致");
        return false;
    }

    net_.opt.num_threads = threads_;
    net_.opt.use_vulkan_compute = false;
    if (net_.load_param(param_path.c_str()) != 0)
    {
        setError(error, "ncnn param 加载失败：" + param_path);
        return false;
    }
    if (net_.load_model(bin_path.c_str()) != 0)
    {
        setError(error, "ncnn bin 加载失败：" + bin_path);
        return false;
    }

    loaded_ = true;
    return true;
}

bool AnomalyDetector::isLoaded() const
{
    return loaded_;
}

float AnomalyDetector::score(const float* time_major_window,
                             std::size_t value_count) const
{
    if (!loaded_)
    {
        throw std::runtime_error("模型尚未加载");
    }
    const std::size_t expected_count =
        static_cast<std::size_t>(window_size_) * static_cast<std::size_t>(channel_count_);
    if (time_major_window == NULL || value_count != expected_count)
    {
        throw std::invalid_argument("输入窗口长度必须是 60 × 8");
    }

    ncnn::Mat input(window_size_, 1, channel_count_);
    if (input.empty())
    {
        throw std::runtime_error("ncnn 输入内存分配失败");
    }

    for (int channel = 0; channel < channel_count_; ++channel)
    {
        float* output_channel = input.channel(channel).row(0);
        const float channel_mean = mean_[channel];
        const float channel_std = stddev_[channel];
        for (int time = 0; time < window_size_; ++time)
        {
            const float raw = time_major_window[
                static_cast<std::size_t>(time) * channel_count_ + channel];
            if (!std::isfinite(raw))
            {
                throw std::invalid_argument("输入窗口包含 NaN 或无穷值");
            }
            output_channel[time] = (raw - channel_mean) / channel_std;
        }
    }

    ncnn::Extractor extractor = net_.create_extractor();
    if (extractor.input("sensor_window", input) != 0)
    {
        throw std::runtime_error("ncnn 输入写入失败");
    }
    ncnn::Mat output;
    if (extractor.extract("anomaly_logit", output) != 0 || output.empty())
    {
        throw std::runtime_error("ncnn 推理失败");
    }

    return sigmoid(output[0]);
}

float AnomalyDetector::score(const std::vector<float>& time_major_window) const
{
    return score(time_major_window.data(), time_major_window.size());
}

bool AnomalyDetector::isAnomaly(float probability) const
{
    return probability >= threshold_probability_;
}

float AnomalyDetector::thresholdProbability() const
{
    return threshold_probability_;
}

int AnomalyDetector::windowSize() const
{
    return window_size_;
}

int AnomalyDetector::channelCount() const
{
    return channel_count_;
}

bool AnomalyDetector::parseConfig(const std::string& config_path, std::string* error)
{
    window_size_ = 0;
    channel_count_ = 0;
    threads_ = 1;
    threshold_probability_ = 0.0f;
    threshold_logit_ = 0.0f;
    mean_.clear();
    stddev_.clear();

    bool has_probability = false;
    bool has_logit = false;

    std::ifstream stream(config_path.c_str());
    if (!stream)
    {
        setError(error, "模型配置无法打开：" + config_path);
        return false;
    }

    std::string line;
    while (std::getline(stream, line))
    {
        line = trim(line);
        if (line.empty() || line[0] == '#')
        {
            continue;
        }
        const std::string::size_type separator = line.find('=');
        if (separator == std::string::npos)
        {
            setError(error, "模型配置行格式错误：" + line);
            return false;
        }
        const std::string key = trim(line.substr(0, separator));
        const std::string value = trim(line.substr(separator + 1));

        bool ok = true;
        if (key == "window_size")
            ok = parseInteger(value, window_size_);
        else if (key == "channels")
            ok = parseInteger(value, channel_count_);
        else if (key == "threads")
            ok = parseInteger(value, threads_);
        else if (key == "threshold_probability")
        {
            ok = parseFloat(value, threshold_probability_);
            has_probability = ok;
        }
        else if (key == "threshold_logit")
        {
            ok = parseFloat(value, threshold_logit_);
            has_logit = ok;
        }
        else if (key == "mean")
            ok = parseFloatList(value, mean_);
        else if (key == "std")
            ok = parseFloatList(value, stddev_);

        if (!ok)
        {
            setError(error, "模型配置值解析失败：" + key);
            return false;
        }
    }

    if (window_size_ <= 0 || channel_count_ <= 0 || threads_ <= 0 ||
        !has_probability || !has_logit)
    {
        setError(error, "模型配置缺少必要字段");
        return false;
    }
    if (threshold_probability_ <= 0.0f || threshold_probability_ >= 1.0f)
    {
        setError(error, "异常概率阈值必须位于 (0, 1)");
        return false;
    }
    for (std::size_t i = 0; i < stddev_.size(); ++i)
    {
        if (!(stddev_[i] > 0.0f))
        {
            setError(error, "标准化标准差必须大于 0");
            return false;
        }
    }
    return true;
}

} // namespace edge_ai
