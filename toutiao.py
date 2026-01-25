import urllib.request
import urllib.parse
import re
import json
import random
import binascii
import base64
import os

# crc32 右移函数（兼容Python3整数处理）
def right_shift(val, n):
    return val >> n if val >= 0 else (val + 0x100000000) >> n

# 获取页面HTML内容（适配Python3 urllib）
def getHtml(url):
    # 添加请求头，模拟浏览器访问（避免被反爬）
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    page = urllib.request.urlopen(req)
    html = page.read().decode('utf-8')  # Python3需指定编码解码bytes
    return html

# 从HTML中提取videoid
def getVideoid(html):
    reg = r'videoid:(.+?),'
    videore = re.compile(reg)
    videolist = re.findall(videore, html)
    for videourl in videolist:
        lens = len(videourl) - 1
        videourl = videourl[1: lens]
        return videourl

# 解析视频JSON接口数据
def parseVideoJson(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    html = urllib.request.urlopen(req)
    htmlstr = html.read().decode('utf-8')
    dictstr = json.loads(htmlstr)
    print('videojson:', dictstr)  # Python3 print改为函数
    datastr = dictstr['data']
    dict_videolist = datastr['video_list']
    dict_video1 = dict_videolist['video_1']
    main_url = dict_video1['main_url']
    return main_url

# 下载视频到本地
def downLoadVideoFromURL(url):
    try:
        path = os.getcwd()
        file_name = str(random.random()) + '.mp4'
        dest_dir = os.path.join(path, file_name)
        # Python3 urllib.request.urlretrieve 适配
        urllib.request.urlretrieve(url, dest_dir)
        print(f'视频下载完成，保存路径：{dest_dir}')
    except Exception as e:  # 捕获具体异常并打印
        print(f'\tError retrieving the URL: {url}, 异常信息: {str(e)}')

# Step 1: 获取页面HTML
html = getHtml('http://www.toutiao.com/a7141306745929859592/')
with open('video.html', 'w', encoding='utf-8') as file_object:  # Python3文件操作指定编码
    file_object.write(html)

# Step 2: 提取videoid
videoid = getVideoid(html)
print('videoid:', videoid)

# Step 3: 计算crc32校验值
if videoid:  # 增加非空判断，避免后续报错
    r = str(random.random())[2:]
    url = 'http://i.snssdk.com/video/urls/v/1/toutiao/mp4/%s' % videoid
    # Python3 urlparse 移到 urllib.parse
    n = urllib.parse.urlparse(url).path + '?r=' + r
    # Python3 crc32需先编码为bytes
    c = binascii.crc32(n.encode('utf-8'))
    s = right_shift(c, 0)
    print("crc32:", s)

    # Step 4: 解析视频JSON接口
    mainvideourl = parseVideoJson(url + '?r=%s&s=%s' % (r, s))

    # Step 5: Base64解码真实视频链接
    # Python3 base64解码需处理bytes
    videourl = base64.b64decode(mainvideourl).decode('utf-8')
    print('videourl:', videourl)

    # Step 6: 下载视频
    downLoadVideoFromURL(videourl)
else:
    print('未提取到videoid，请检查视频链接是否有效')