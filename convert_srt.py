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
import datetime
import codecs
import re
from mafan import text as mafan_text
from enum import Enum, unique
from pysrt import SubRipFile
from pysrt import SubRipItem
from pysrt import SubRipTime

@unique
class SRT_TYPE(Enum):
    Chinese = 0
    English = 1
    Both = 2
    Unknown = 3


def join_lines(txtsub1, txtsub2):
    if (len(txtsub1) > 0) & (len(txtsub2) > 0):
        return txtsub1 + '\n' + txtsub2
    else:
        return txtsub1 + txtsub2


def find_subtitle(subtitle, from_t, to_t, lo=0):
    i = lo
    while (i < len(subtitle)):
        if (subtitle[i].start >= to_t):
            break

        if (subtitle[i].start <= from_t) & (to_t  <= subtitle[i].end):
            return subtitle[i].text, i
        i += 1

    return "", i


def merge_subtitle(sub_a, sub_b, delta):
    out = SubRipFile()
    intervals = [item.start.ordinal for item in sub_a]
    intervals.extend([item.end.ordinal for item in sub_a])
    intervals.extend([item.start.ordinal for item in sub_b])
    intervals.extend([item.end.ordinal for item in sub_b])
    intervals.sort()

    j = k = 0
    for i in range(1, len(intervals)):
        start = SubRipTime.from_ordinal(intervals[i-1])
        end = SubRipTime.from_ordinal(intervals[i])

        if (end-start) > delta:
            text_a, j = find_subtitle(sub_a, start, end, j)
            text_b, k = find_subtitle(sub_b, start, end, k)

            text = join_lines(text_a, text_b)
            if len(text) > 0:
                item = SubRipItem(0, start, end, text)
                out.append(item)

    out.clean_indexes()
    return out

def validate_file_name(file_name):
    rstr = r"[\/\\\:\*\?\"\<\>\|]"  # '/ \ : * ? " < > |'
    new_title = re.sub(rstr, "_", file_name)
    new_title = new_title.replace('\'','')
    new_title = new_title.replace('"', '')
    return new_title


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
        encode = get_file_encode(srt_file_name)
        subtitle_list = pysrt.open(srt_file_name, encoding=encode)
        srt_info_duration = (subtitle_list[-1].end - subtitle_list[0].start).to_time()
        srt_duration = srt_info_duration.hour * 3600 + srt_info_duration.minute * 60 + srt_info_duration.second
        if (video_duration > srt_duration + 5000):
            print('视频长度远大于字幕最大长度，可能不匹配')
            return

        for subtitle in subtitle_list:
            # 长度小于3秒的 不带字幕的 前1分钟内的 不切
            if subtitle.duration.seconds < 3 or len(subtitle.text_without_tags) == 0 or subtitle.start.minutes < 1:
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
                        subtitle_text_chn += mafan_text.simplify(line.strip())
                    else:
                        subtitle_text_chn += line.strip()
                else:
                    subtitle_text_eng += line.strip()

            # 没翻译 或者没原文 不切
            if len(subtitle_text_eng) < 4 or len(subtitle_text_chn) == 0:
                continue

            # if subtitle_text_eng.startswith('Then I got really freaked out, and that'):
            #     print(subtitle_text_eng)
            # else:
            #     continue

            # 如果要保存 必须去掉特殊字符
            subtitle_text_eng = validate_file_name(subtitle_text_eng)

            if os.name == 'nt':
                subtext = file_name + '\\' + subtitle_text_eng + '.mp4'
            else:
                subtext = file_name + '/' + subtitle_text_eng + '.mp4'

            # 如果有同名的文件 以最后一个为准
            if os.path.isfile(subtext):
                os.remove(subtext)

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

def insensitive_glob(pattern):
    if os.name == 'nt':
        def either(c):
            return '[%s%s]' % (c.lower(), c.upper()) if c.isalpha() else c

        return glob.glob(''.join(map(either, pattern)))
    else:
        return glob.glob(pattern)


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
        # https://www.zhihu.com/question/36368902
        with open(file_string, errors='ignore') as ass_file:
            srt_str = asstosrt.convert(ass_file)
        srt_file_name = file_name + '_converted_ass.srt'
        if os.path.isfile(srt_file_name):
            os.remove(srt_file_name)
        with open(srt_file_name, "w", encoding='utf-8', newline='\n') as srt_file:
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

# 随机挑选10个字幕出来 如果这些字幕中系又带中文又带英文 则代表是双语字幕
def check_srt_type(file_name):
    export = pysrt.open(file_name, encoding=get_file_encode(file_name))
    random_length = min(10, len(export))
    if random_length == 0:
        return SRT_TYPE.Unknown
    random_list = random_int_list(0, len(export) - 1, random_length)
    chn_list = []
    eng_list = []
    both_list = []
    for random_int in random_list:
        subtitle = export[random_int]
        subtitle_text_lines = subtitle.text_without_tags.split('\n')
        has_chn = False
        has_eng = False
        for line in subtitle_text_lines:
            if check_contain_chinese(line):
                has_chn = True
            else:
                has_eng = True

            if has_chn == True and has_eng == True:
                both_list.append(random_int)
            elif has_eng == True:
                eng_list.append(random_int)
            elif has_chn == True:
                chn_list.append(random_int)

    if len(both_list) > random_length * 0.7:
        return SRT_TYPE.Both
    if len(chn_list) > random_length * 0.7:
        return SRT_TYPE.Chinese
    if len(eng_list) > random_length * 0.7:
        return SRT_TYPE.English
    return SRT_TYPE.Unknown

def merge_srt(chn_file, eng_file, output_file):
    delta = SubRipTime(milliseconds=500)
    subs_a = SubRipFile.open(chn_file)
    subs_b = SubRipFile.open(eng_file)
    out = merge_subtitle(subs_a, subs_b, delta)
    if os.path.isfile(output_file):
        os.remove(output_file)
    out.save(output_file, encoding='utf8')



if __name__ == "__main__":
    global all_video_files
    all_video_files = []

    # 遍历所有文件夹内的视频文件并存入 all_video_files
    get_video_files('.')

    # 如果有ass，尝试转成一个srt，这是为了防止下载下来的只有ass带翻译字幕 而srt没有，作为一个备选
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        ass_file_name_list = insensitive_glob(file_name + '*.ass')
        if len(ass_file_name_list) > 0:
            for ass_file_name in ass_file_name_list:
                convert_ass_to_srt(ass_file_name)

    # 视频可能带内嵌字幕，可以从视频里直接尝试提取，改后缀 _export_srt，然后保存，作为一个备选
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)

        video_info_cmd = 'ffprobe -v quiet -print_format json -show_format -show_streams "{}"'.format(video)
        video_json = json.loads(run_command(video_info_cmd))
        if not 'streams' in video_json:
            continue
        video_stream_list = video_json['streams']
        video_srt_index_list = []
        video_ass_index_list = []
        for video_stream in video_stream_list:
            if video_stream['codec_name'] == 'subrip':
                video_srt_index_list.append(int(video_stream['index']))
            elif video_stream['codec_name'] == 'ass':
                video_ass_index_list.append(int(video_stream['index']))

        export_subtitle_list = []
        for video_sub_index in video_srt_index_list:
            srt_file_name = file_name + '_' + str(video_sub_index) + '_export_srt.srt'
            if os.path.isfile(srt_file_name):
                os.remove(srt_file_name)
            cmd = 'ffmpeg -i "{}" -map 0:{} "{}"'.format(video, str(video_sub_index), srt_file_name)
            print(cmd)
            rst = run_command(cmd)
            print(rst)
            export_subtitle_list.append(srt_file_name)

        for video_sub_index in video_ass_index_list:
            ass_file_name = file_name + '_' + str(video_sub_index) + '_export_ass.ass'
            if os.path.isfile(ass_file_name):
                os.remove(ass_file_name)
            cmd = 'ffmpeg -i "{}" -map 0:{} "{}"'.format(video, str(video_sub_index), ass_file_name)
            print(cmd)
            rst = run_command(cmd)
            print(rst)
            convert_ass_to_srt(ass_file_name)

        # 挑选出内嵌字幕的中英文
        for export_file in export_subtitle_list:
            type = check_srt_type(export_file)

            if type == SRT_TYPE.Chinese:
                # 是中文
                correct_srt_file_name = file_name + '_export_chn.srt'
                if os.path.isfile(correct_srt_file_name):
                    os.remove(correct_srt_file_name)
                os.rename(export_file, correct_srt_file_name)

            if type == SRT_TYPE.English:
                # 是英文
                correct_srt_file_name = file_name + '_export_eng.srt'
                if os.path.isfile(correct_srt_file_name):
                    os.remove(correct_srt_file_name)
                os.rename(export_file, correct_srt_file_name)

            if type == SRT_TYPE.Both:
                correct_srt_file_name = file_name + '_export_both.srt'
                if os.path.isfile(correct_srt_file_name):
                    os.remove(correct_srt_file_name)
                os.rename(export_file, correct_srt_file_name)

        correct_srt_chn_file_name = file_name + '_export_chn.srt'
        correct_srt_eng_file_name = file_name + '_export_eng.srt'
        correct_srt_both_file_name = file_name + '_export_both.srt'

        # 导出的字幕只有中文和英文，没有中英双语
        if not os.path.isfile(correct_srt_both_file_name) and os.path.isfile(correct_srt_chn_file_name) and os.path.isfile(correct_srt_eng_file_name):
            merge_srt(correct_srt_chn_file_name, correct_srt_eng_file_name, correct_srt_both_file_name)


    # 尝试挑选出一个带原文和译文（是简体中文的）的最佳 srt 出来
    srt_video_files = []
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        srt_file_name_list = insensitive_glob(file_name + '*.srt')
        for srt_index, srt_file_name in enumerate(srt_file_name_list):
            if os.path.isfile(srt_file_name):
                type = check_srt_type(srt_file_name)
                if type == SRT_TYPE.Chinese:
                    # 是中文
                    correct_srt_file_name = file_name + '_inner_chn.srt'
                    if not correct_srt_file_name == srt_file_name and os.path.isfile(correct_srt_file_name):
                        os.remove(correct_srt_file_name)
                    os.rename(srt_file_name, correct_srt_file_name)
                elif type == SRT_TYPE.English:
                    # 是英文
                    correct_srt_file_name = file_name + '_inner_eng.srt'
                    if not correct_srt_file_name == srt_file_name and os.path.isfile(correct_srt_file_name):
                        os.remove(correct_srt_file_name)
                    os.rename(srt_file_name, correct_srt_file_name)
                elif type == SRT_TYPE.Both:
                    correct_srt_file_name = file_name + '_correct_' + str(srt_index) + '.srt'
                    if not correct_srt_file_name == srt_file_name and os.path.isfile(correct_srt_file_name):
                        os.remove(correct_srt_file_name)
                    os.rename(srt_file_name, correct_srt_file_name)
                else:
                    correct_srt_file_name = ''


            inner_srt_chn_file_name = file_name + '_inner_chn.srt'
            inner_srt_eng_file_name = file_name + '_inner_eng.srt'
            inner_srt_both_file_name_list = insensitive_glob(file_name + '_correct_*.srt')
            if len(inner_srt_both_file_name_list) == 0 and os.path.isfile(inner_srt_chn_file_name) and os.path.isfile(inner_srt_eng_file_name):
                merge_srt(inner_srt_chn_file_name, inner_srt_eng_file_name, file_name + '_correct_' + str(1) + '.srt')


        correct_srt_file_list = insensitive_glob(file_name + '_correct_*.srt')
        # 有多个符合条件的中英双语，筛选出简体的，如果没有，才用繁体，和之前一样的算法
        if len(correct_srt_file_list) > 0:
            srt_video_files.append(video)
            finall_correct_srt_file_name = file_name + '_correct' + '.srt'
            for correct_srt_file in correct_srt_file_list:
                if check_srt_type(correct_srt_file) == SRT_TYPE.Both:
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


