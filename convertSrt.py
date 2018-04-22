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

def process_video_with_srt(video_file):
    file_name, file_extension = os.path.splitext(video_file)
    srt_file_name = file_name + '.srt'

    with open(srt_file_name, 'r') as srt_file:
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
                    subtitle_text_chn = line.strip()
                else:
                    subtitle_text_eng = line.strip()

            # 没翻译 或者没原文 也不会做切割
            if len(subtitle_text_eng) < 4 or len(subtitle_text_chn) == 0:
                continue

            if os.name == 'nt':
                subtext = file_name + '\\' + subtitle_text_eng + '.mp4'
            else:
                subtext = file_name + '/' + subtitle_text_eng + '.mp4'

            cmd = 'ffmpeg -i "{}" -ss {} -to {} -filter:v scale=560:-1 -vcodec mpeg4 -crf 40 -async 1 -strict -2 -preset veryslow -acodec copy "{}"'.format(video_file, start_time, end_time, subtext)
            rst = run_command(cmd)
            print(cmd)


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


# 如果字幕不是 srt 格式的，先转成 srt，如果有同名的 srt ，则删除重新创建
def convert_ass_to_srt(file_string):
    file_name, file_extension = os.path.splitext(file_string)
    if file_extension.endswith('ass'):
        with open(file_string) as ass_file:
            srt_str = asstosrt.convert(ass_file)
        srt_file_name = file_name + '.srt'
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


if __name__ == "__main__":
    global all_video_files
    all_video_files = []

    get_video_files('.')

    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        srt_file_name = file_name + '.srt'
        ass_file_name = file_name + '.ass'
        if not os.path.isfile(srt_file_name):
            # 如果没有srt尝试转一个srt
            if os.path.isfile(ass_file_name):
                convert_ass_to_srt(ass_file_name)

    srt_video_files = []
    # 准备工作，先转成 utf8 避免python解析失败
    for video in all_video_files:
        file_name, file_extension = os.path.splitext(video)
        srt_file_name = file_name + '.srt'
        if os.path.isfile(srt_file_name):
            srt_video_files.append(video)
            # 检查是否是 utf8 若不是，则转码
            encode = ''
            with open(srt_file_name, 'rb') as utf8:
                rawdata = b''.join([utf8.readline() for _ in range(20)])
                encode = chardet.detect(rawdata)['encoding']

            if not encode.lower().startswith('utf'):
                with open(srt_file_name, encoding=encode) as fobj:
                    content = fobj.read()
                with open(srt_file_name, 'w', encoding='utf-8') as fobj:
                    fobj.write(content)


    for video in srt_video_files:
        process_video_with_srt(video)


