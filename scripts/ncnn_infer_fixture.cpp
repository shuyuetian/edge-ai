// 使用 ncnn 运行固定窗口夹具，供 Python 比较数值一致性。

#include "net.h"

#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

static std::vector<float> read_float_file(const char* path)
{
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream)
    {
        std::fprintf(stderr, "无法打开输入文件: %s\n", path);
        std::exit(1);
    }
    const std::streamsize size = stream.tellg();
    stream.seekg(0, std::ios::beg);
    std::vector<float> values(static_cast<size_t>(size) / sizeof(float));
    if (!stream.read(reinterpret_cast<char*>(values.data()), size))
    {
        std::fprintf(stderr, "读取输入文件失败: %s\n", path);
        std::exit(1);
    }
    return values;
}

int main(int argc, char** argv)
{
    if (argc != 8 && argc != 9)
    {
        std::fprintf(
            stderr,
            "用法: %s <param> <bin> <input.f32> <output.f32> <count> <window> <channels> [blob]\n",
            argv[0]);
        return 1;
    }

    const char* param_path = argv[1];
    const char* bin_path = argv[2];
    const char* input_path = argv[3];
    const char* output_path = argv[4];
    const int count = std::atoi(argv[5]);
    const int window_size = std::atoi(argv[6]);
    const int channels = std::atoi(argv[7]);
    const char* blob_name = argc == 9 ? argv[8] : "anomaly_logit";
    const size_t values_per_sample =
        static_cast<size_t>(window_size) * static_cast<size_t>(channels);

    const std::vector<float> input = read_float_file(input_path);
    if (input.size() < values_per_sample * static_cast<size_t>(count))
    {
        std::fprintf(stderr, "输入元素数量少于 count × window × channels\n");
        return 1;
    }

    ncnn::Net net;
    net.opt.num_threads = 4;
    net.opt.use_vulkan_compute = false;
    if (net.load_param(param_path) != 0 || net.load_model(bin_path) != 0)
    {
        std::fprintf(stderr, "ncnn 模型加载失败\n");
        return 1;
    }

    std::ofstream output(output_path, std::ios::binary);
    if (!output)
    {
        std::fprintf(stderr, "无法创建输出文件: %s\n", output_path);
        return 1;
    }

    for (int index = 0; index < count; index++)
    {
        // 部署输入为 [channels, 1, time]，与 ncnn Mat(w,h,c) 布局一致。
        ncnn::Mat input_mat(window_size, 1, channels);
        std::memcpy(
            input_mat.data,
            input.data() + values_per_sample * static_cast<size_t>(index),
            values_per_sample * sizeof(float));

        ncnn::Extractor extractor = net.create_extractor();
        if (extractor.input("sensor_window", input_mat) != 0)
        {
            std::fprintf(stderr, "第 %d 个样本输入失败\n", index);
            return 1;
        }
        ncnn::Mat output_mat;
        if (extractor.extract(blob_name, output_mat) != 0)
        {
            std::fprintf(stderr, "第 %d 个样本推理失败\n", index);
            return 1;
        }
        if (index == 0)
        {
            std::fprintf(
                stderr,
                "blob=%s dims=%d w=%d h=%d c=%d elempack=%d total=%zu\n",
                blob_name,
                output_mat.dims,
                output_mat.w,
                output_mat.h,
                output_mat.c,
                output_mat.elempack,
                output_mat.total());
        }
        size_t value_count = 1;
        if (output_mat.dims == 1) value_count = output_mat.w;
        if (output_mat.dims == 2) value_count = output_mat.w * output_mat.h;
        if (output_mat.dims == 3)
            value_count = output_mat.w * output_mat.h * output_mat.c;
        value_count *= static_cast<size_t>(output_mat.elempack);
        output.write(
            reinterpret_cast<const char*>(output_mat.data),
            static_cast<std::streamsize>(value_count * sizeof(float)));
    }

    if (!output)
    {
        std::fprintf(stderr, "写入输出文件失败\n");
        return 1;
    }
    return 0;
}
