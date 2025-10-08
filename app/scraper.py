import asyncio
import csv
import uuid
import re
import random
from bilibili_api import video, comment, Credential
from bilibili_api.exceptions import ApiException, ResponseCodeException

def parse_cookie_str(cookie_str: str):
    # ... (此函数无改动)
    sessdata = re.search(r"SESSDATA=([^;]+)", cookie_str)
    bili_jct = re.search(r"bili_jct=([^;]+)", cookie_str)
    dedeuserid = re.search(r"DedeUserID=([^;]+)", cookie_str)
    
    return {
        "sessdata": sessdata.group(1) if sessdata else None,
        "bili_jct": bili_jct.group(1) if bili_jct else None,
        "dedeuserid": dedeuserid.group(1) if dedeuserid else None,
    }

def _save_comments_to_csv(comments_list: list, bvid: str):
    # ... (此函数无改动)
    if not comments_list:
        return None
        
    filename = f"comments_{bvid}_{uuid.uuid4().hex[:8]}.csv"
    
    processed_comments = []
    for cmt in comments_list:
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
        return filename
    except IOError:
        return None

async def get_comments_scraper(bvid: str, cookie: str, scrape_sub_comments: bool, stop_event: asyncio.Event):
    """
    异步爬取B站视频评论（最终健壮版）。
    """
    all_collected_comments = []
    successful_completion = False

    try:
        # --- 1. 初始化 ---
        yield "LOG: 启动 bilibili-api 库模式..."
        cookie_parts = parse_cookie_str(cookie)
        credential = Credential(**cookie_parts)
        
        yield f"LOG: 正在获取视频 {bvid} 的信息..."
        v = video.Video(bvid=bvid, credential=credential)
        video_info = await v.get_info()
        aid = video_info['aid']
        total_comments = video_info.get('stat', {}).get('reply', 0)
        yield f"LOG: 目标锁定:《{video_info['title']}》，总评论数约为 {total_comments}。"

        # --- 辅助函数 ---
        async def _process_sub_comments_for_chunk(main_comments_chunk: list):
            if stop_event.is_set():
                yield "WARN: 收到中断信号，跳过本块楼中楼处理。"
                return
            
            comments_with_replies = [cmt for cmt in main_comments_chunk if cmt.get("rcount", 0) > 0]
            if not scrape_sub_comments or not comments_with_replies:
                return

            yield f"LOG: 正在处理本块 {len(comments_with_replies)} 条主评论下的楼中楼回复..."
            semaphore = asyncio.Semaphore(10)
            
            async def fetch_all_sub_comments(main_comment):
                async with semaphore:
                    rpid = main_comment['rpid']
                    sub_cmt_obj = comment.Comment(oid=aid, rpid=rpid, type_=comment.CommentResourceType.VIDEO, credential=credential)
                    sub_comments_list = []
                    sub_page = 1
                    while True:
                        if stop_event.is_set(): break # 每次请求前检查，加速中断
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        try:
                            sub_c = await sub_cmt_obj.get_sub_comments(page_index=sub_page)
                        except Exception:
                            break
                        sub_replies = sub_c.get('replies')
                        if not sub_replies: break
                        sub_comments_list.extend(sub_replies)
                        sub_page += 1
                        await asyncio.sleep(random.uniform(0.8, 2))
                    return sub_comments_list

            tasks = [fetch_all_sub_comments(cmt) for cmt in comments_with_replies]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            newly_added_sub_comments = []
            for res in results:
                if isinstance(res, list):
                    newly_added_sub_comments.extend(res)
                elif isinstance(res, Exception):
                    yield f"WARN: 在获取某个楼中楼时发生错误: {res}"

            yield f"LOG: 本块楼中楼处理完毕，新增 {len(newly_added_sub_comments)} 条楼中楼回复。"
            all_collected_comments.extend(newly_added_sub_comments)

        # --- 2. 按不同排序方式，分阶段爬取与处理 ---
        seen_rpids = set()
        order_types = { comment.OrderType.TIME: "时间", comment.OrderType.LIKE: "热度" }

        for order, order_name in order_types.items():
            if stop_event.is_set():
                yield "WARN: 收到中断信号，跳过后续排序方式。"
                break
            
            yield f"LOG: --- 开始按【{order_name}】排序爬取主评论 ---"
            page = 1
            chunk_size = random.randint(8, 15)
            page_in_chunk_count = 0
            main_comments_this_chunk = []

            while True:
                # 【优化点 1】统一在此处检查中断信号，逻辑更清晰
                if stop_event.is_set():
                    yield "WARN: 收到中断信号，正在结束当前模式的爬取..."
                    # 在中断前，处理掉当前不完整的块
                    async for log_message in _process_sub_comments_for_chunk(main_comments_this_chunk):
                        yield log_message
                    break

                try:
                    yield f"LOG: 正在拉取按【{order_name}】排序的第 {page} 页主评论..."
                    c = await comment.get_comments(aid, comment.CommentResourceType.VIDEO, page, order=order, credential=credential)
                except (ApiException, ResponseCodeException) as e:
                    if hasattr(e, 'code') and e.code == -400 and "max offset exceeded" in str(e):
                        yield f"WARN: 按【{order_name}】排序已达到API分页上限。"
                        # 处理最后一个不完整的块
                        async for log_message in _process_sub_comments_for_chunk(main_comments_this_chunk):
                            yield log_message
                        break
                    else:
                        yield f"ERROR: 调用API时发生错误: {e}"; return

                replies = c.get('replies')
                if not replies:
                    yield f"LOG: 按【{order_name}】排序的所有主评论已拉取完毕。"
                    # 处理最后一个不完整的块
                    async for log_message in _process_sub_comments_for_chunk(main_comments_this_chunk):
                        yield log_message
                    break
                
                # --- 数据处理逻辑 (无改动) ---
                unique_replies_this_page = []
                for cmt in replies:
                    if cmt['rpid'] not in seen_rpids:
                        unique_replies_this_page.append(cmt)
                        seen_rpids.add(cmt['rpid'])
                
                if unique_replies_this_page:
                    main_comments_this_chunk.extend(unique_replies_this_page)
                    all_collected_comments.extend(unique_replies_this_page)
                    yield f"LOG: 第 {page} 页拉取完成，新增 {len(unique_replies_this_page)} 条主评论，当前总计 {len(all_collected_comments)} 条。"
                
                page += 1
                page_in_chunk_count += 1

                # --- 分块处理与暂停逻辑 ---
                if page_in_chunk_count >= chunk_size:
                    async for log_message in _process_sub_comments_for_chunk(main_comments_this_chunk):
                        yield log_message
                    
                    main_comments_this_chunk = []
                    page_in_chunk_count = 0
                    chunk_size = random.randint(8, 15)
                    
                    long_sleep_time = random.uniform(15, 30)
                    yield f"LOG: 已完成一个爬取块，将暂停 {long_sleep_time:.2f} 秒..."
                    
                    # 【优化点 2】将长时暂停改为可中断的暂停
                    for _ in range(int(long_sleep_time)):
                        if stop_event.is_set():
                            break
                        await asyncio.sleep(1)
                else:
                    await asyncio.sleep(random.uniform(2, 4))
        
        if not stop_event.is_set():
            yield f"LOG: 所有流程正常完成！"
            successful_completion = True

    finally:
        # --- 3. 最终保存 ---
        if all_collected_comments:
            if successful_completion:
                yield f"LOG: 爬取完成！最终总计 {len(all_collected_comments)} 条评论，正在保存到文件..."
            else:
                yield f"WARN: 进程被中断或发生错误。正在紧急保存已爬取的 {len(all_collected_comments)} 条评论..."

            filename = _save_comments_to_csv(all_collected_comments, bvid)
            
            if filename:
                yield f"SUCCESS: 文件保存成功！"
                yield f"DOWNLOAD:{filename}"
            else:
                yield f"ERROR: 文件保存失败！"
        else:
            if not successful_completion:
                yield "WARN: 进程已终止，且未爬取到任何评论。"