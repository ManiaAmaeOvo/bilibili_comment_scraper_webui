document.addEventListener("DOMContentLoaded", () => {
    // 元素获取
    const getCookieBtn = document.getElementById("get-cookie-btn");
    const startBtn = document.getElementById("start-btn");
    const stopBtn = document.getElementById("stop-btn");
    const bvidInput = document.getElementById("bvid-input");
    const cookieInput = document.getElementById("cookie-input");
    const subCommentsCheckbox = document.getElementById("sub-comments-checkbox");
    const logConsole = document.getElementById("log-console");
    
    let scrapeEventSource;
    let cookieWebSocket;
    let currentTaskId = null;

    function addLog(message, type) {
        const now = new Date();
        const timestamp = `[${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
        const p = document.createElement('p');
        p.className = `log-${type}`;
        p.innerHTML = `<span class="log-timestamp">${timestamp}</span> ${message}`;
        logConsole.appendChild(p);
        logConsole.scrollTop = logConsole.scrollHeight;
    }
    
    function setScrapingState(isScraping) {
        startBtn.disabled = isScraping;
        startBtn.querySelector('.btn-text').textContent = isScraping ? "正在爬取" : "开始爬取";
        startBtn.classList.toggle('loading', isScraping);
        
        stopBtn.classList.toggle('hidden', !isScraping);
        stopBtn.disabled = !isScraping;

        getCookieBtn.disabled = isScraping;
        bvidInput.disabled = isScraping;
        cookieInput.disabled = isScraping;
        subCommentsCheckbox.disabled = isScraping;
    }

    // --- 自动获取Cookie逻辑 ---
    getCookieBtn.addEventListener("click", () => {
        getCookieBtn.disabled = true;
        getCookieBtn.classList.add('loading'); // 添加加载动画
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
            getCookieBtn.classList.remove('loading'); // 移除加载动画
        };

        cookieWebSocket.onerror = (error) => {
            console.error("WebSocket Error:", error);
            addLog("<strong>WebSocket连接发生错误。</strong>", "error");
            getCookieBtn.disabled = false;
            getCookieBtn.classList.remove('loading');
        };
    });

    // --- 停止爬取逻辑 ---
    stopBtn.addEventListener("click", () => {
        if (currentTaskId) {
            addLog("正在发送停止信号，程序将在完成当前小任务后保存...", "warn");
            stopBtn.disabled = true;
            fetch(`/stop/${currentTaskId}`, { method: 'POST' });
        }
    });

    // --- 开始爬取逻辑 ---
    startBtn.addEventListener("click", () => {
        const bvid = bvidInput.value.trim();
        const cookie = cookieInput.value.trim();
        const scrapeSubComments = subCommentsCheckbox.checked;

        if (!bvid || !cookie) {
            alert("Cookie和BV号都不能为空！");
            return;
        }
        
        if (scrapeEventSource) {
            scrapeEventSource.close();
        }

        logConsole.innerHTML = '';
        addLog("正在初始化爬取任务...", "info");
        setScrapingState(true);
        
        const scrapeUrl = `/scrape/?bvid=${encodeURIComponent(bvid)}&cookie=${encodeURIComponent(cookie)}&scrape_sub_comments=${scrapeSubComments}`;
        scrapeEventSource = new EventSource(scrapeUrl);

        scrapeEventSource.onmessage = function(event) {
            const message = event.data;
            
            if (message.startsWith("TASK_ID:")) {
                currentTaskId = message.split(":")[1];
                return;
            }

            let logClass = "info";
            let logContent = message.replace(/^LOG: /, '');

            if (message.startsWith("ERROR:") || message.startsWith("WARN:")) {
                logClass = message.startsWith("ERROR:") ? "error" : "warn";
                logContent = message.replace(/^(ERROR|WARN): /, '');
            } else if (message.startsWith("SUCCESS:")) {
                logClass = "success";
                logContent = message.replace(/^SUCCESS: /, '');
            } else if (message.startsWith("DOWNLOAD:")) {
                const filename = message.split(":")[1];
                logClass = "download";
                logContent = `<a href="/download/${filename}" download><strong>点击此处下载评论文件: ${filename}</strong></a>`;
                
                scrapeEventSource.close();
                setScrapingState(false);
                currentTaskId = null;
            }
            
            addLog(logContent, logClass);
        };

        scrapeEventSource.onerror = function(error) {
            addLog("<strong>与服务器的连接中断或发生错误。</strong>", "error");
            if(scrapeEventSource) scrapeEventSource.close();
            setScrapingState(false);
            currentTaskId = null;
        };
    });
});