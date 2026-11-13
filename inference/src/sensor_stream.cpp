#include "sensor_stream.h"

#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <limits>
#include <sstream>
#include <stdexcept>

#include <unordered_map>

namespace edge_ai {

namespace {

const char* const SENSOR_COLUMNS[] = {
    "Accelerometer1RMS",
    "Accelerometer2RMS",
    "Current",
    "Pressure",
    "Temperature",
    "Thermocouple",
    "Voltage",
    "Volume Flow RateRMS",
};

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

std::vector<std::string> parseDelimited(
    const std::string& line,
    char delimiter,
    std::size_t line_number)
{
    std::vector<std::string> fields;
    std::string field;
    bool quoted = false;
    for (std::size_t i = 0; i < line.size(); ++i)
    {
        const char character = line[i];
        if (quoted)
        {
            if (character == '"')
            {
                if (i + 1 < line.size() && line[i + 1] == '"')
                {
                    field.push_back('"');
                    ++i;
                }
                else
                {
                    quoted = false;
                }
            }
            else
            {
                field.push_back(character);
            }
        }
        else if (character == '"')
        {
            if (!trim(field).empty())
            {
                throw std::runtime_error(
                    "第 " + std::to_string(line_number) +
                    " 行引号位置非法");
            }
            quoted = true;
        }
        else if (character == delimiter)
        {
            fields.push_back(trim(field));
            field.clear();
        }
        else
        {
            field.push_back(character);
        }
    }
    if (quoted)
    {
        throw std::runtime_error(
            "第 " + std::to_string(line_number) + " 行引号未闭合");
    }
    fields.push_back(trim(field));
    return fields;
}

std::size_t countUnquoted(const std::string& line, char target)
{
    bool quoted = false;
    std::size_t count = 0;
    for (std::size_t i = 0; i < line.size(); ++i)
    {
        if (line[i] == '"')
        {
            if (quoted && i + 1 < line.size() && line[i + 1] == '"')
            {
                ++i;
            }
            else
            {
                quoted = !quoted;
            }
        }
        else if (!quoted && line[i] == target)
        {
            ++count;
        }
    }
    return count;
}

char detectDelimiter(const std::string& header)
{
    const std::size_t semicolons = countUnquoted(header, ';');
    const std::size_t commas = countUnquoted(header, ',');
    if (semicolons == 0 && commas == 0)
    {
        throw std::runtime_error("CSV 表头没有可识别的分隔符");
    }
    return semicolons >= commas ? ';' : ',';
}

bool isLeapYear(int year)
{
    return (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
}

int daysInMonth(int year, int month)
{
    static const int DAYS[] = {
        31, 28, 31, 30, 31, 30,
        31, 31, 30, 31, 30, 31,
    };
    if (month == 2 && isLeapYear(year))
    {
        return 29;
    }
    return DAYS[month - 1];
}

std::int64_t daysFromCivil(int year, unsigned month, unsigned day)
{
    year -= month <= 2;
    const int era = (year >= 0 ? year : year - 399) / 400;
    const unsigned year_of_era =
        static_cast<unsigned>(year - era * 400);
    const unsigned day_of_year =
        (153 * (month > 2 ? month - 3 : month + 9) + 2) / 5 + day - 1;
    const unsigned day_of_era =
        year_of_era * 365 + year_of_era / 4 -
        year_of_era / 100 + day_of_year;
    return static_cast<std::int64_t>(era) * 146097 +
           static_cast<std::int64_t>(day_of_era) - 719468;
}

std::int64_t parseTimestamp(
    const std::string& value,
    std::size_t line_number)
{
    int year = 0;
    int month = 0;
    int day = 0;
    int hour = 0;
    int minute = 0;
    int second = 0;
    char date_separator = '\0';
    int consumed = 0;
    const int parsed = std::sscanf(
        value.c_str(),
        "%4d-%2d-%2d%c%2d:%2d:%2d%n",
        &year,
        &month,
        &day,
        &date_separator,
        &hour,
        &minute,
        &second,
        &consumed);
    if (parsed != 7 ||
        (date_separator != ' ' && date_separator != 'T') ||
        consumed != static_cast<int>(value.size()) ||
        month < 1 || month > 12 ||
        day < 1 || day > daysInMonth(year, month) ||
        hour < 0 || hour > 23 ||
        minute < 0 || minute > 59 ||
        second < 0 || second > 59)
    {
        throw std::runtime_error(
            "第 " + std::to_string(line_number) +
            " 行时间格式必须是 YYYY-MM-DD HH:MM:SS：" + value);
    }
    return daysFromCivil(year, static_cast<unsigned>(month),
                         static_cast<unsigned>(day)) *
               86400 +
           hour * 3600 + minute * 60 + second;
}

std::string formatTimestamp(std::int64_t timestamp_seconds)
{
    const std::time_t raw = static_cast<std::time_t>(timestamp_seconds);
    std::tm value;
    if (gmtime_r(&raw, &value) == NULL)
    {
        throw std::runtime_error("无法格式化插值时间戳");
    }
    char buffer[32];
    if (std::strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &value) == 0)
    {
        throw std::runtime_error("无法格式化插值时间戳");
    }
    return std::string(buffer);
}

float parseSensorValue(
    const std::string& value,
    std::size_t line_number,
    const std::string& column)
{
    errno = 0;
    char* end = NULL;
    const double parsed = std::strtod(value.c_str(), &end);
    if (value.empty() || end == value.c_str() || *end != '\0' ||
        errno == ERANGE ||
        !std::isfinite(parsed) ||
        parsed < -static_cast<double>(std::numeric_limits<float>::max()) ||
        parsed > static_cast<double>(std::numeric_limits<float>::max()))
    {
        throw std::runtime_error(
            "第 " + std::to_string(line_number) +
            " 行字段 " + column + " 不是有效有限数值：" + value);
    }
    return static_cast<float>(parsed);
}

std::size_t findColumn(
    const std::unordered_map<std::string, std::size_t>& columns,
    const std::string& name,
    bool required)
{
    const std::unordered_map<std::string, std::size_t>::const_iterator found =
        columns.find(name);
    if (found == columns.end())
    {
        if (required)
        {
            throw std::runtime_error("CSV 表头缺少字段：" + name);
        }
        return std::numeric_limits<std::size_t>::max();
    }
    return found->second;
}

} // namespace

CsvSensorReader::CsvSensorReader(
    std::istream& input,
    std::size_t expected_channel_count)
    : input_(&input),
      delimiter_(';'),
      timestamp_column_(0),
      line_number_(0)
{
    if (expected_channel_count == 0)
    {
        throw std::invalid_argument("CSV 通道数必须大于 0");
    }

    std::string header;
    while (std::getline(*input_, header))
    {
        ++line_number_;
        header = trim(header);
        if (!header.empty())
        {
            break;
        }
    }
    if (header.empty())
    {
        throw std::runtime_error("CSV 文件为空");
    }
    if (header.size() >= 3 &&
        static_cast<unsigned char>(header[0]) == 0xEF &&
        static_cast<unsigned char>(header[1]) == 0xBB &&
        static_cast<unsigned char>(header[2]) == 0xBF)
    {
        header.erase(0, 3);
    }

    delimiter_ = detectDelimiter(header);
    const std::vector<std::string> names =
        parseDelimited(header, delimiter_, line_number_);
    std::unordered_map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < names.size(); ++i)
    {
        if (!columns.insert(std::make_pair(names[i], i)).second)
        {
            throw std::runtime_error("CSV 表头存在重复字段：" + names[i]);
        }
    }

    const std::size_t datetime_column = findColumn(columns, "datetime", false);
    timestamp_column_ =
        datetime_column != std::numeric_limits<std::size_t>::max()
            ? datetime_column
            : findColumn(columns, "timestamp", true);

    sensor_columns_.resize(expected_channel_count);
    for (std::size_t i = 0; i < expected_channel_count; ++i)
    {
        sensor_columns_[i] = findColumn(columns, SENSOR_COLUMNS[i], true);
    }
}

bool CsvSensorReader::read(SensorRecord& record)
{
    std::string line;
    while (std::getline(*input_, line))
    {
        ++line_number_;
        if (trim(line).empty())
        {
            continue;
        }
        const std::vector<std::string> fields =
            parseDelimited(line, delimiter_, line_number_);
        for (std::size_t i = 0; i < sensor_columns_.size(); ++i)
        {
            if (sensor_columns_[i] >= fields.size())
            {
                throw std::runtime_error(
                    "第 " + std::to_string(line_number_) +
                    " 行字段数量不足");
            }
        }
        if (timestamp_column_ >= fields.size())
        {
            throw std::runtime_error(
                "第 " + std::to_string(line_number_) +
                " 行缺少时间戳");
        }

        record.timestamp_text = fields[timestamp_column_];
        record.timestamp_seconds =
            parseTimestamp(record.timestamp_text, line_number_);
        record.sensor_values.resize(sensor_columns_.size());
        for (std::size_t i = 0; i < sensor_columns_.size(); ++i)
        {
            record.sensor_values[i] = parseSensorValue(
                fields[sensor_columns_[i]],
                line_number_,
                SENSOR_COLUMNS[i]);
        }
        record.source_line = line_number_;
        return true;
    }
    return false;
}

char CsvSensorReader::delimiter() const
{
    return delimiter_;
}

SlidingWindowStream::SlidingWindowStream(
    int window_size,
    int channel_count,
    int stride)
    : window_size_(window_size),
      channel_count_(channel_count),
      stride_(stride),
      has_last_(false),
      last_timestamp_(0),
      segment_samples_(0),
      processed_samples_(0),
      segment_count_(0)
{
    if (window_size_ < 2 || channel_count_ < 1 || stride_ < 1)
    {
        throw std::invalid_argument(
            "窗口大小必须至少为 2，通道和步长必须大于 0");
    }
    last_values_.resize(static_cast<std::size_t>(channel_count_));
}

void SlidingWindowStream::push(
    std::int64_t timestamp_seconds,
    const std::string& timestamp_text,
    const float* values,
    std::size_t value_count,
    std::vector<StreamWindow>* windows)
{
    if (values == NULL ||
        value_count != static_cast<std::size_t>(channel_count_))
    {
        throw std::invalid_argument("流式输入通道数量错误");
    }
    if (windows == NULL)
    {
        throw std::invalid_argument("窗口输出容器不能为空");
    }
    for (int channel = 0; channel < channel_count_; ++channel)
    {
        if (!std::isfinite(values[channel]))
        {
            throw std::invalid_argument("流式输入包含 NaN 或无穷值");
        }
    }

    if (!has_last_)
    {
        reset();
        ++segment_count_;
        append(timestamp_seconds, timestamp_text, values, windows);
        return;
    }

    const std::int64_t delta = timestamp_seconds - last_timestamp_;
    if (delta <= 0)
    {
        throw std::invalid_argument("流式时间戳必须严格递增");
    }
    if (delta == 1)
    {
        append(timestamp_seconds, timestamp_text, values, windows);
    }
    else if (delta == 2)
    {
        std::vector<float> interpolated(
            static_cast<std::size_t>(channel_count_));
        for (int channel = 0; channel < channel_count_; ++channel)
        {
            interpolated[channel] =
                (last_values_[channel] + values[channel]) * 0.5f;
        }
        const std::string interpolated_time =
            formatTimestamp(last_timestamp_ + 1);
        append(
            last_timestamp_ + 1,
            interpolated_time,
            interpolated.data(),
            windows);
        append(timestamp_seconds, timestamp_text, values, windows);
    }
    else
    {
        reset();
        ++segment_count_;
        append(timestamp_seconds, timestamp_text, values, windows);
    }
}

void SlidingWindowStream::append(
    std::int64_t timestamp_seconds,
    const std::string& timestamp_text,
    const float* values,
    std::vector<StreamWindow>* windows)
{
    if (rolling_values_.size() >=
        static_cast<std::size_t>(window_size_ * channel_count_))
    {
        rolling_values_.erase(
            rolling_values_.begin(),
            rolling_values_.begin() + channel_count_);
    }
    rolling_values_.insert(
        rolling_values_.end(), values, values + channel_count_);

    ++segment_samples_;
    ++processed_samples_;
    last_timestamp_ = timestamp_seconds;
    last_values_.assign(values, values + channel_count_);
    has_last_ = true;

    if (segment_samples_ >= window_size_ &&
        (segment_samples_ - window_size_) % stride_ == 0)
    {
        StreamWindow window;
        window.timestamp_seconds = timestamp_seconds;
        window.timestamp_text = timestamp_text;
        window.sensor_values = rolling_values_;
        windows->push_back(window);
    }
}

void SlidingWindowStream::reset()
{
    rolling_values_.clear();
    segment_samples_ = 0;
    has_last_ = false;
}

int SlidingWindowStream::segmentCount() const
{
    return segment_count_;
}

std::int64_t SlidingWindowStream::processedSamples() const
{
    return processed_samples_;
}

} // namespace edge_ai
