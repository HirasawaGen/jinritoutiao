'''
视频的字段
title: 标题
id: 视频id  (key)
url: 视频url  (其实用id就能组成url,但是那些请求参数我也不知道是有什么用,那这里还是新增一个url比较好)
category: 视频分区
md5: 视频md5值
path: 视频在本地的存储路径
uploader: 上传者的id
likes: 点赞数
views: 播放量
upload_time: 上传时间


组成url时：https://www.toutiao.com/video/{id}
FIXME: 把上面说的这乱七八糟的改成dao层操作
'''