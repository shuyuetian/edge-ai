#include "sensor_stream.h"

#include <cmath>
#include <iostream>
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

std::vector<float> values(float value)
{
    return std::vector<float>(1, value);
}

void testCsvReader()
{
    std::istringstream csv(
        "\xEF\xBB\xBF"
        "datetime,Voltage,Accelerometer1RMS,"
        "Accelerometer2RMS,Current,Pressure,Temperature,"
        "Thermocouple,Volume Flow RateRMS\n"
        "2020-03-09 10:34:33,244.091,0.027,0.039,0.871,"
        "0.0547,75.49,25.83,32.0\n");
    edge_ai::CsvSensorReader reader(csv, 8);
    edge_ai::SensorRecord record;
    require(reader.delimiter() == ',', "应识别逗号分隔符");
    require(reader.read(record), "应读取一行传感器数据");
    require(record.timestamp_text == "2020-03-09 10:34:33",
            "时间戳文本应保留");
    require(record.sensor_values.size() == 8, "应读取 8 路传感器");
    require(std::fabs(record.sensor_values[0] - 0.027f) < 1e-6f,
            "第一路应按 Accelerometer1RMS 映射");
    require(std::fabs(record.sensor_values[2] - 0.871f) < 1e-6f,
            "第三路应按 Current 映射");
    require(std::fabs(record.sensor_values[6] - 244.091f) < 1e-5f,
            "第七路应按 Voltage 映射");
    require(!reader.read(record), "一行数据后应到达 EOF");
}

void testSemicolonCsv()
{
    std::istringstream csv(
        "datetime;Accelerometer1RMS;Accelerometer2RMS;Current;"
        "Pressure;Temperature;Thermocouple;Voltage;"
        "Volume Flow RateRMS\n"
        "2020-03-09 10:34:33;0.1;0.2;1.4;0.3;75.5;25.8;244.0;32.0\n");
    edge_ai::CsvSensorReader reader(csv, 8);
    edge_ai::SensorRecord record;
    require(reader.delimiter() == ';', "应识别分号分隔符");
    require(reader.read(record), "应读取 SKAB 分号格式");
    require(record.timestamp_seconds > 0, "应解析 Unix 时间");
}

void testWindowAndInterpolation()
{
    edge_ai::SlidingWindowStream stream(3, 1, 1);
    std::vector<edge_ai::StreamWindow> windows;
    std::vector<float> v = values(1.0f);

    stream.push(0, "1970-01-01 00:00:00", v.data(), v.size(), &windows);
    stream.push(1, "1970-01-01 00:00:01",
                values(2.0f).data(), 1, &windows);
    stream.push(2, "1970-01-01 00:00:02",
                values(3.0f).data(), 1, &windows);
    require(windows.size() == 1, "满足窗口后应产生一次结果");
    require(windows[0].sensor_values[0] == 1.0f &&
            windows[0].sensor_values[1] == 2.0f &&
            windows[0].sensor_values[2] == 3.0f,
            "窗口内容顺序错误");

    windows.clear();
    stream.push(4, "1970-01-01 00:00:04",
                values(5.0f).data(), 1, &windows);
    require(windows.size() == 2, "两秒间隔应插入一个采样并分别触发窗口");
    require(std::fabs(windows[0].sensor_values[2] - 4.0f) < 1e-6f,
            "插值结果应为相邻采样均值");
}

void testGapAndStride()
{
    edge_ai::SlidingWindowStream stream(3, 1, 2);
    std::vector<edge_ai::StreamWindow> windows;
    stream.push(0, "1970-01-01 00:00:00",
                values(1.0f).data(), 1, &windows);
    stream.push(1, "1970-01-01 00:00:01",
                values(2.0f).data(), 1, &windows);
    stream.push(2, "1970-01-01 00:00:02",
                values(3.0f).data(), 1, &windows);
    require(windows.size() == 1, "第 3 个采样应触发窗口");
    stream.push(3, "1970-01-01 00:00:03",
                values(4.0f).data(), 1, &windows);
    require(windows.size() == 1, "步长 2 不应每行触发窗口");
    stream.push(4, "1970-01-01 00:00:04",
                values(5.0f).data(), 1, &windows);
    require(windows.size() == 2, "第 5 个采样应再次触发窗口");
    stream.push(5, "1970-01-01 00:00:05",
                values(6.0f).data(), 1, &windows);
    require(windows.size() == 2, "步长 2 时第 6 个采样不应触发窗口");

    windows.clear();
    stream.push(10, "1970-01-01 00:00:10",
                values(7.0f).data(), 1, &windows);
    require(windows.empty(), "长间隔后应重新累积窗口");
    require(stream.segmentCount() == 2, "长间隔应增加一个独立段");
}

void testTimeOrderValidation()
{
    edge_ai::SlidingWindowStream stream(3, 1, 1);
    std::vector<edge_ai::StreamWindow> windows;
    stream.push(10, "1970-01-01 00:00:10",
                values(1.0f).data(), 1, &windows);
    bool caught = false;
    try
    {
        stream.push(9, "1970-01-01 00:00:09",
                    values(2.0f).data(), 1, &windows);
    }
    catch (const std::invalid_argument&)
    {
        caught = true;
    }
    require(caught, "时间戳倒退应被拒绝");
}

} // namespace

int main()
{
    try
    {
        testCsvReader();
        testSemicolonCsv();
        testWindowAndInterpolation();
        testGapAndStride();
        testTimeOrderValidation();
    }
    catch (const std::exception& exception)
    {
        std::cerr << exception.what() << "\n";
        return 1;
    }
    std::cout << "流式 CSV 与滑窗验收通过\n";
    return 0;
}
