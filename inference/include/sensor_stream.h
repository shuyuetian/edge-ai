#ifndef EDGE_AI_SENSOR_STREAM_H_
#define EDGE_AI_SENSOR_STREAM_H_

#include <cstddef>
#include <cstdint>
#include <istream>
#include <string>
#include <vector>

namespace edge_ai {

struct SensorRecord
{
    std::int64_t timestamp_seconds;
    std::string timestamp_text;
    std::vector<float> sensor_values;
    std::size_t source_line;
};

struct StreamWindow
{
    std::int64_t timestamp_seconds;
    std::string timestamp_text;
    std::vector<float> sensor_values;
};

class CsvSensorReader
{
public:
    CsvSensorReader(std::istream& input, std::size_t expected_channel_count);

    bool read(SensorRecord& record);
    char delimiter() const;

private:
    CsvSensorReader(const CsvSensorReader&);
    CsvSensorReader& operator=(const CsvSensorReader&);

private:
    std::istream* input_;
    char delimiter_;
    std::size_t timestamp_column_;
    std::vector<std::size_t> sensor_columns_;
    std::size_t line_number_;
};

class SlidingWindowStream
{
public:
    SlidingWindowStream(int window_size, int channel_count, int stride);

    void push(std::int64_t timestamp_seconds,
              const std::string& timestamp_text,
              const float* values,
              std::size_t value_count,
              std::vector<StreamWindow>* windows);

    int segmentCount() const;
    std::int64_t processedSamples() const;

private:
    void append(std::int64_t timestamp_seconds,
                const std::string& timestamp_text,
                const float* values,
                std::vector<StreamWindow>* windows);
    void reset();

private:
    int window_size_;
    int channel_count_;
    int stride_;
    bool has_last_;
    std::int64_t last_timestamp_;
    std::vector<float> last_values_;
    std::vector<float> rolling_values_;
    std::int64_t segment_samples_;
    std::int64_t processed_samples_;
    int segment_count_;
};

} // namespace edge_ai

#endif // EDGE_AI_SENSOR_STREAM_H_
