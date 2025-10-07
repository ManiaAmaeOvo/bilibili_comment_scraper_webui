import asyncio
import csv
import uuid
import re
from bilibili_api import video, comment, Credential

def parse_cookie_str(cookie_str: str):
    """从原始Cookie字符串中解析出关键字段"""
    sessdata = re.search(r"SESSDATA=([^;]+)", cookie_str)
    bili_jct = re.search(r"bili_jct=([^;]+)", cookie_str)
    dedeuserid = re.search(r"DedeUserID=([^;]+)", cookie_str)
    
    return {
        "sessdata": sessdata.group(1) if sessdata else None,
        "bili_jct": bili_jct.group(1) if bili_jct else None,
        "dedeuserid": dedeuserid.group(1) if dedeuserid else None,
    }

async def get_comments_scraper(bvid: str, cookie: str, scrape_sub_comments: bool):
    """
    异步爬取B站视频评论。

    Args:
        bvid (str): 视频的BV号。
        cookie (str): 包含SESSDATA, bili_jct, DedeUserID的用户Cookie字符串。
        scrape_sub_comments (bool): 是否爬取楼中楼（二级评论）。
    """
    yield "LOG: 启动 bilibili-api 库模式..."
    all_comments = []
    
    try:
        # --- 1. 初始化身份凭证 ---
        yield "LOG: 正在解析用户Cookie并初始化身份凭证..."
        cookie_parts = parse_cookie_str(cookie)
        if not all(cookie_parts.values()):
            yield "ERROR: Cookie信息不完整，缺少SESSDATA, bili_jct或DedeUserID。"
            return
        credential = Credential(**cookie_parts)
        
        # --- 2. 获取视频信息 ---
        yield f"LOG: 正在获取视频 {bvid} 的信息..."
        v = video.Video(bvid=bvid, credential=credential)
        video_info = await v.get_info()
        aid = video_info['aid']
        total_comments = video_info.get('stat', {}).get('reply', 0)
        yield f"LOG: 目标锁定:《{video_info['title']}》，总评论数约为 {total_comments}。"

        # --- 3. 分页爬取主评论 ---
        page = 1
        main_comments_with_replies = [] # 存储有楼中楼回复的主评论
        
        while True:
            yield f"LOG: 正在拉取第 {page} 页主评论..."
            c = await comment.get_comments(aid, comment.CommentResourceType.VIDEO, page, credential=credential)
            
            replies = c.get('replies')
            if not replies:
                yield "LOG: 所有主评论已拉取完毕。"
                break
            
            # 筛选出有楼中楼的评论，为后续爬取做准备
            if scrape_sub_comments:
                for cmt in replies:
                    if cmt.get("rcount", 0) > 0:
                        main_comments_with_replies.append(cmt)
            
            all_comments.extend(replies)
            yield f"LOG: 第 {page} 页拉取完成，当前已获取 {len(all_comments)} 条主评论。"
            page += 1
            await asyncio.sleep(1) # 礼貌性延时

        # --- 4. 根据 scrape_sub_comments 参数决定是否爬取楼中楼 ---
        if scrape_sub_comments and main_comments_with_replies:
            yield f"LOG: 开始并发拉取 {len(main_comments_with_replies)} 条主评论下的所有楼中楼回复..."
            
            async def fetch_all_sub_comments(main_comment):
                """
                辅助函数，用于分页获取单条主评论下的所有楼中楼回复。
                """
                rpid = main_comment['rpid']
                sub_cmt_obj = comment.Comment(oid=aid, rpid=rpid, type_=comment.CommentResourceType.VIDEO, credential=credential)
                sub_comments_list = []
                sub_page = 1
                while True:
                    # 使用 get_sub_comments 方法并传入页码
                    sub_c = await sub_cmt_obj.get_sub_comments(page_index=sub_page)
                    sub_replies = sub_c.get('replies')
                    if not sub_replies:
                        break # 如果没有更多回复了，就跳出循环
                    sub_comments_list.extend(sub_replies)
                    sub_page += 1
                    await asyncio.sleep(0.5) # 轻微延时
                return sub_comments_list

            # 使用 asyncio.gather 实现高性能并发
            tasks = [fetch_all_sub_comments(cmt) for cmt in main_comments_with_replies]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            sub_comments_count = 0
            for res in results:
                if isinstance(res, list):
                    all_comments.extend(res)
                    sub_comments_count += len(res)
                elif isinstance(res, Exception):
                    yield f"WARN: 在获取某个楼中楼时发生错误: {res}"

            yield f"LOG: 楼中楼回复拉取完成，新增 {sub_comments_count} 条，当前总计 {len(all_comments)} 条评论。"
        elif scrape_sub_comments:
            yield "LOG: 未发现任何含有楼中楼回复的主评论。"
        else:
            yield "LOG: 已跳过爬取楼中楼回复。"


        # --- 5. 格式化并保存文件 ---
        if all_comments:
            filename = f"comments_{bvid}_{uuid.uuid4().hex[:8]}.csv"
            yield f"LOG: 爬取完成！最终总计 {len(all_comments)} 条评论，正在保存到文件 {filename} ..."
            
            # 格式化数据以便写入
            processed_comments = []
            for cmt in all_comments:
                processed_comments.append({
                    'rpid': cmt['rpid'],
                    'parent_rpid': cmt['parent'],
                    'username': cmt['member']['uname'],
                    'content': cmt['content']['message'],
                    'like_count': cmt['like'],
                    'timestamp': cmt['ctime'],
                    'ip_location': cmt.get('reply_control', {}).get('location', '未知')
                })

            try:
                with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                    fieldnames = ['rpid', 'parent_rpid', 'username', 'content', 'like_count', 'timestamp', 'ip_location']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(processed_comments)
                yield f"SUCCESS: 文件保存成功！"
                yield f"DOWNLOAD:{filename}"
            except IOError as e:
                yield f"ERROR: 保存文件时出错: {e}"
        else:
            yield "LOG: 未爬取到任何评论。"

    except Exception as e:
        yield f"ERROR: 发生未知错误: {e}"