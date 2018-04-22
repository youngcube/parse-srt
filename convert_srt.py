#!/usr/bin/python3
# -*- coding: utf-8 -*-
import subprocess
import shlex
import os
import asstosrt
import pysrt
import json
import shutil
import chardet
import glob
import random
from mafan import text as mafan_text

# 处理同名的视频和字幕，已经做好检测，是带原文和译文的
def process_video_with_srt(video_file):
    file_name, file_extension = os.path.splitext(video_file)
    srt_file_name = file_name + '_correct.srt'

    with open(srt_file_name, 'r', encoding=get_file_encode(srt_file_name)) as srt_file:
        # 字幕列表格式
        # 0 = {str}
        # '11\n'
        # 1 = {str}
        # '00:00:21,770 --> 00:00:23,270\n'
        # 2 = {str}
        # '是我\n'
        # 3 = {str}
        # 'Hey, it’s me.\n'

        if os.path.isdir(file_name):
            shutil.rmtree(file_name, ignore_errors=True)
        os.makedirs(file_name)

        video_info_cmd = 'ffprobe -v quiet -print_format json -show_format -show_streams "{}"'.format(video_file)
        video_duration = float(json.loads(run_command(video_info_cmd))['format']['duration'])

        subtitle_list = pysrt.open(srt_file_name)
        srt_info_duration = (subtitle_list[-1].end - subtitle_list[0].start).to_time()
        srt_duration = srt_info_duration.hour * 3600 + srt_info_duration.minute * 60 + srt_info_duration.second
        if (video_duration > srt_duration + 5000):
            print('视频长度远大于字幕最大长度，可能不匹配')
            return

        for subtitle in subtitle_list:
            # 长度小于3秒的 不带字幕的 不切
            if subtitle.duration.seconds < 3 or len(subtitle.text_without_tags) == 0:
                continue
            start_time = '{}'.format(subtitle.start).split(',')[0]
            # 加上1秒的缓冲 可能不够
            subtitle.end.seconds += 1
            end_time = '{}'.format(subtitle.end).split(',')[0]

            # 根据是否有中文判断是否是翻译
            subtitle_lines = subtitle.text_without_tags.split('\n')
            subtitle_text_chn = ''
            subtitle_text_eng = ''
            for line in subtitle_lines:
                if check_contain_chinese(line):
                    if mafan_text.is_traditional(line):
                        subtitle_text_chn = mafan_text.simplify(line.strip())
                    else:
                        subtitle_text_chn = line.strip()
                else:
                    subtitle_text_eng = line.strip()

            # 没翻译 或者没原文 不切
            if len(subtitle_text_eng) < 4 or len(subtitle_text_chn) == 0:
                continue

            if os.name == 'nt':
                subtext = file_name + '\\' + subtitle_text_eng + '.mp4'
            else:
                subtext = file_name + '/' + subtitle_text_eng + '.mp4'

            cmd = 'ffmpeg -i "{}" -ss {} -to {} -filter:v scale=560:-1 -vcodec mpeg4 -crf 40 -async 1 -strict -2 -preset veryslow -acodec copy "{}"'.format(video_file, start_time, end_time, subtext)
            print(cmd)
            rst = run_command(cmd)
            print(rst)


def run_command(cmd):
    try:
        output = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        rst = output.stdout.read()
        return rst
    except:
        return ''


def check_contain_chinese(check_str):
    for ch in check_str:
        if u'\u4e00' <= ch <= u'\u9fff':
            return True
    return False

def get_file_encode(file_name):
    encode = ''
    with open(file_name, 'rb') as utf8:
        rawdata = b''.join([utf8.readline() for _ in range(20)])
        encode = chardet.detect(rawdata)['encoding']
    return encode


# 如果字幕不是 srt 格式的，先转成 srt，转换后的名字带后缀 _converted_ass
def convert_ass_to_srt(file_string):
    file_name, file_extension = os.path.splitext(file_string)
    if file_extension.endswith('ass'):
        encode = get_file_encode(file_string)
        with open(file_string, encoding=encode) as ass_file:
            srt_str = asstosrt.convert(ass_file)
        srt_file_name = file_name + '_converted_ass.srt'
        if os.path.isfile(srt_file_name):
            os.remove(srt_file_name)
        with open(srt_file_name, "w") as srt_file:
            srt_file.write(srt_str)


def get_video_files(root_dir):
    for lists in os.listdir(root_dir):
        path = os.path.join(root_dir, lists)
        if os.path.isdir(path):
            get_video_files(path)
        if path.endswith('.mp4') or path.endswith('.mkv'):
            all_video_files.append(path)


def random_int_list(start, stop, length):
    start, stop = (int(start), int(stop)) if start <= stop else (int(stop), int(start))
    length = int(abs(length)) if length else 0
    random_list = []
    for i in range(length):
        random_list.append(random.randint(start, stop))
    return random_list


if __name__ == "__main__":
    global all_video_files
    all_video_files = []

    # 遍历所有文件夹内的视频文件并存入 all_video_files
    get_video_files('.')

    # 如果有ass，尝试转成一个srt，这是为了防止下载下来的只有ass带翻译字幕 而srt没有，作为一个备选
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        ass_file_name_list = glob.glob(file_name + '*.ass')
        if len(ass_file_name_list) > 0:
            for ass_file_name in ass_file_name_list:
                convert_ass_to_srt(ass_file_name)

    # 视频可能带内嵌字幕，可以从视频里直接尝试提取，改后缀 _export_srt，然后保存，作为一个备选
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        srt_file_name = file_name + '_export_srt.srt'
        cmd = 'ffmpeg -i "{}" -map 0:s:0 "{}"'.format(video, srt_file_name)
        rst = run_command(cmd)
        print(cmd)

    # 尝试挑选出一个带原文和译文（是简体中文的）的最佳 srt 出来
    # 随机挑选10个字幕出来 如果这些字幕>1行 且带一个中文行 的数量有70%以上 则代表是翻译字幕
    srt_video_files = []
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        srt_file_name_list = glob.glob(file_name + '*.srt')
        for srt_index, srt_file_name in enumerate(srt_file_name_list):
            if os.path.isfile(srt_file_name):
                subtitle_list = pysrt.open(srt_file_name)
                random_length = min(10, len(subtitle_list))
                if random_length == 0:
                    continue
                random_list = random_int_list(0, len(subtitle_list) - 1, random_length)
                has_trans_list = []
                for random_int in random_list:
                    subtitle = subtitle_list[random_int]
                    subtitle_text_lines = subtitle.text_without_tags.split('\n')
                    if len(subtitle_text_lines) < 2:
                        continue
                    has_chn = False
                    has_eng = False
                    for line in subtitle_text_lines:
                        if check_contain_chinese(line):
                            has_chn = True
                        else:
                            has_eng = True

                    if has_eng == True and has_chn == True:
                        has_trans_list.append(random_int)

                if len(has_trans_list) > random_length * 0.7:
                    # 是中英双语字幕，改成后缀处理
                    correct_srt_file_name = file_name + '_correct_' + str(srt_index) + '.srt'
                    if os.path.isfile(correct_srt_file_name):
                        os.remove(correct_srt_file_name)
                    os.rename(srt_file_name, correct_srt_file_name)


        correct_srt_file_list = glob.glob(file_name + '_correct_*.srt')
        # 有多个符合条件的中英双语，筛选出简体的，如果没有，才用繁体，和之前一样的算法
        if len(correct_srt_file_list) > 0:
            srt_video_files.append(video)
            finall_correct_srt_file_name = file_name + '_correct' + '.srt'
            for correct_srt_file in correct_srt_file_list:
                subtitle_list = pysrt.open(correct_srt_file)
                random_length = min(10, len(subtitle_list))
                random_list = random_int_list(0, len(subtitle_list) - 1, random_length)
                has_chs_list = []
                for random_int in random_list:
                    subtitle = subtitle_list[random_int]
                    subtitle_text_lines = subtitle.text_without_tags.split('\n')
                    if len(subtitle_text_lines) < 2:
                        continue
                    has_chs = False
                    for line in subtitle_text_lines:
                        if mafan_text.is_simplified(line):
                            has_chs_list.append(random_int)

                if len(has_chs_list) > random_length * 0.7:
                    if os.path.isfile(finall_correct_srt_file_name):
                        os.remove(finall_correct_srt_file_name)
                    os.rename(correct_srt_file, finall_correct_srt_file_name)


            # 全部检测完毕 没有一个符合的 说明是繁体，只能用繁体了
            if not os.path.isfile(finall_correct_srt_file_name):
                os.rename(correct_srt_file_list[0], finall_correct_srt_file_name)

    if len(srt_video_files) == 0:
        print('没有一个符合条件的中英双语字幕的视频文件，停止处理')
    else:
        for video in srt_video_files:
            process_video_with_srt(video)

