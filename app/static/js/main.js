document.addEventListener("DOMContentLoaded", () => {
    // 元素获取
    const startBtn = document.getElementById("start-btn");
    const getCookieBtn = document.getElementById("get-cookie-btn");
    const bvidInput = document.getElementById("bvid-input");
    const cookieInput = document.getElementById("cookie-input");
    const subCommentsCheckbox = document.getElementById("sub-comments-checkbox"); // 获取复选框元素
    const logConsole = document.getElementById("log-console");
    
    let scrapeEventSource;
    let cookieWebSocket;

    function addLog(message, type) {
        // 1. 获取当前时间并格式化为 HH:MM:SS
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        const timestamp = `[${hours}:${minutes}:${seconds}]`;
    
        // 2. 创建一个新的 <p> 元素来存放日志
        const p = document.createElement('p');
        p.className = `log-${type}`;
        
        // 3. 创建一个带自定义class的span来包裹时间戳，并与消息拼接
        //    使用 innerHTML 可以正确渲染消息中的链接等HTML标签
        p.innerHTML = `<span class="log-timestamp">${timestamp}</span> ${message}`;
        
        logConsole.appendChild(p);
        logConsole.scrollTop = logConsole.scrollHeight; // 自动滚动到底部
    }

    // --- 自动获取Cookie逻辑 ---
    getCookieBtn.addEventListener("click", () => {
        getCookieBtn.disabled = true;
        getCookieBtn.innerText = "正在获取...";
        logConsole.innerHTML = ''; 
        addLog("正在初始化连接...", "info");

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        cookieWebSocket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/get-cookie`);

        cookieWebSocket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            switch (message.type) {
                case 'status':
                    addLog(message.data, "info");
                    break;
                case 'cookie_success':
                    addLog("<strong>成功获取Cookie！</strong>", "success");
                    cookieInput.value = message.data;
                    cookieWebSocket.close();
                    break;
                case 'error':
                    addLog(`<strong>错误:</strong> ${message.data}`, "error");
                    cookieWebSocket.close();
                    break;
            }
        };
        
        cookieWebSocket.onclose = () => {
            getCookieBtn.disabled = false;
            getCookieBtn.innerText = "自动获取Cookie";
        };

        cookieWebSocket.onerror = (error) => {
            console.error("WebSocket Error:", error);
            addLog("<strong>WebSocket连接发生错误。</strong>", "error");
        };
    });


    // --- 开始爬取逻辑 ---
    startBtn.addEventListener("click", () => {
        const bvid = bvidInput.value.trim();
        const cookie = cookieInput.value.trim();
        const scrapeSubComments = subCommentsCheckbox.checked; // 【修改点】获取复选框状态

        if (!bvid || !cookie) {
            alert("Cookie和BV号都不能为空！");
            return;
        }
        
        if (scrapeEventSource) {
            scrapeEventSource.close();
        }

        logConsole.innerHTML = '';
        addLog("正在初始化爬取任务...", "info");

        startBtn.disabled = true;
        startBtn.innerText = "正在爬取...";
        
        // 【修改点】将scrape_sub_comments参数添加到URL中
        const scrapeUrl = `/scrape/?bvid=${encodeURIComponent(bvid)}&cookie=${encodeURIComponent(cookie)}&scrape_sub_comments=${scrapeSubComments}`;
        scrapeEventSource = new EventSource(scrapeUrl);

        scrapeEventSource.onmessage = function(event) {
            const message = event.data;
            let logClass = "info";
            let logContent = message.replace(/^LOG: /, '');

            if (message.startsWith("ERROR:")) {
                logClass = "error";
                logContent = message.replace(/^ERROR: /, '');
            } else if (message.startsWith("SUCCESS:")) {
                logClass = "success";
                logContent = message.replace(/^SUCCESS: /, '');
            } else if (message.startsWith("DOWNLOAD:")) {
                const filename = message.split(":")[1];
                logClass = "download";
                logContent = `<a href="/download/${filename}" download><strong>点击此处下载评论文件: ${filename}</strong></a>`;
                startBtn.disabled = false;
                startBtn.innerText = "开始爬取";
                scrapeEventSource.close();
            }
            
            addLog(logContent, logClass);
        };

        scrapeEventSource.onerror = function(error) {
            addLog("<strong>与服务器的连接中断或发生错误。</strong>", "error");
            if(scrapeEventSource) scrapeEventSource.close();
            startBtn.disabled = false;
            startBtn.innerText = "开始爬取";
        };
    });
});