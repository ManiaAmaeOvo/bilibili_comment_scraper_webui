import asyncio
from fastapi import FastAPI, Request, Query, WebSocket, WebSocketDisconnect
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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 【修改点】增加了 scrape_sub_comments 参数
@app.get("/scrape/")
async def scrape_endpoint(
    bvid: str = Query(...), 
    cookie: str = Query(...),
    scrape_sub_comments: bool = Query(False) # 接收新参数
):
    decoded_cookie = urllib.parse.unquote(cookie)
    async def log_generator():
        # 将新参数传递给爬虫核心
        async for log_message in get_comments_scraper(bvid, decoded_cookie, scrape_sub_comments):
            yield log_message
            await asyncio.sleep(0.01)
    return EventSourceResponse(log_generator())

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