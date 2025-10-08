import asyncio
import uuid
from fastapi import FastAPI, Request, Query, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from app.scraper import get_comments_scraper
import urllib.parse
from playwright.async_api import async_playwright

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# --- 新增 ---
# 用于存储每个正在进行的爬取任务的停止信号事件
# 键是任务ID，值是 asyncio.Event 对象
scraping_events = {}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/scrape/")
async def scrape_endpoint(
    request: Request, # 添加 request 参数以检测连接断开
    bvid: str = Query(...), 
    cookie: str = Query(...),
    scrape_sub_comments: bool = Query(False)
):
    # --- 新增：为每个任务创建唯一的ID和停止事件 ---
    task_id = str(uuid.uuid4())
    stop_event = asyncio.Event()
    scraping_events[task_id] = stop_event

    async def log_generator():
        # 第一条消息，立即将任务ID发送给前端
        yield f"TASK_ID:{task_id}"
        
        try:
            # 将 stop_event 传递给爬虫核心
            async for log_message in get_comments_scraper(
                bvid, 
                urllib.parse.unquote(cookie), 
                scrape_sub_comments, 
                stop_event
            ):
                # 在发送每条日志前，检查客户端是否已断开连接
                if await request.is_disconnected():
                    # 如果连接已断开，设置停止事件，让爬虫优雅退出
                    stop_event.set()
                    print(f"Connection lost for task {task_id}, sending stop signal.")
                    break # 停止发送日志
                yield log_message
        finally:
            # --- 新增：任务结束后（无论成功、失败还是中断），都从字典中清理 ---
            if task_id in scraping_events:
                del scraping_events[task_id]
            print(f"Task {task_id} finished and cleaned up.")

    return EventSourceResponse(log_generator())

# --- 新增：用于接收停止信号的API端点 ---
@app.post("/stop/{task_id}")
async def stop_scrape(task_id: str):
    """
    根据任务ID，找到对应的停止事件并设置它。
    """
    if task_id in scraping_events:
        scraping_events[task_id].set()
        return {"message": f"Stop signal sent to task {task_id}."}
    
    # 如果任务ID不存在（可能已完成），返回404
    raise HTTPException(status_code=404, detail="Task not found or already completed.")


@app.get("/download/{filename}")
async def download_file(filename: str):
    return FileResponse(path=filename, media_type='application/octet-stream', filename=filename)

@app.websocket("/ws/get-cookie")
async def websocket_get_cookie(websocket: WebSocket):
    await websocket.accept()
    browser = None
    try:
        async with async_playwright() as playwright:
            await websocket.send_json({"type": "status", "data": "正在启动浏览器..."})
            browser = await playwright.chromium.launch(channel="chrome", headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            await websocket.send_json({"type": "status", "data": "正在打开B站登录页..."})
            await page.goto("https://passport.bilibili.com/login")
            await websocket.send_json({"type": "status", "data": "请在新打开的浏览器窗口中，使用B站App扫描二维码登录..."})
            await page.wait_for_url("https://www.bilibili.com/", timeout=120000)
            
            await websocket.send_json({"type": "status", "data": "登录成功！正在导航到目标视频页面..."})
            target_video = "https://www.bilibili.com/video/BV1BK411L7DJ/"
            await page.goto(target_video)

            cookie_found_future = asyncio.Future()

            async def intercept_comment_api(route):
                request = route.request
                if "api.bilibili.com/x/v2/reply/wbi/main" in request.url:
                    if not cookie_found_future.done():
                        cookie_header = await request.header_value('cookie')
                        cookie_found_future.set_result(cookie_header)
                await route.continue_()

            await page.route("**/*", intercept_comment_api)
            await websocket.send_json({"type": "status", "data": f"已跳转到测试视频页。请在浏览器中向下滑动，直到评论区加载出来。"})
            
            final_cookie = await asyncio.wait_for(cookie_found_future, timeout=60)
            
            await page.unroute("**/*", handler=intercept_comment_api)

            await websocket.send_json({"type": "status", "data": "成功拦截到有效Cookie！"})
            await websocket.send_json({"type": "cookie_success", "data": final_cookie})

    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "data": "操作超时。您可能没有及时滑动加载评论区。"})
    except Exception as e:
        if "Target page, context or browser has been closed" in str(e):
             await websocket.send_json({"type": "status", "data": "浏览器已关闭，操作正常结束。"})
        else:
            await websocket.send_json({"type": "error", "data": f"发生错误: {e}"})
    finally:
        if browser:
            await browser.close()
        await websocket.close()