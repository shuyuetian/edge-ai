#ifndef EDGE_AI_ANOMALY_DETECTOR_H_
#define EDGE_AI_ANOMALY_DETECTOR_H_

#include <cstddef>
#include <string>
#include <vector>

#include "net.h"

namespace edge_ai {

class AnomalyDetector
{
public:
    AnomalyDetector();
    ~AnomalyDetector();

    bool load(const std::string& param_path,
              const std::string& bin_path,
              const std::string& config_path,
              std::string* error = NULL);

    bool isLoaded() const;

    // 输入按时间优先排列：[time0_channel0..7, time1_channel0..7, ...]。
    float score(const float* time_major_window, std::size_t value_count) const;
    float score(const std::vector<float>& time_major_window) const;

    bool isAnomaly(float probability) const;
    float thresholdProbability() const;
    int windowSize() const;
    int channelCount() const;

private:
    AnomalyDetector(const AnomalyDetector&);
    AnomalyDetector& operator=(const AnomalyDetector&);

    bool parseConfig(const std::string& config_path, std::string* error);

private:
    ncnn::Net net_;
    bool loaded_;
    int window_size_;
    int channel_count_;
    int threads_;
    float threshold_probability_;
    float threshold_logit_;
    std::vector<float> mean_;
    std::vector<float> stddev_;
};

} // namespace edge_ai

#endif // EDGE_AI_ANOMALY_DETECTOR_H_
