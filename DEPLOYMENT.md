# B站评论爬虫系统 Docker 部署手册

## 前置条件
- macOS 系统已安装 Docker Desktop
- 项目文件已完整下载到本地

---

## 快速开始

### 1. 启动项目
```bash
cd /path/to/bbcs
docker-compose up -d
```

### 2. 访问应用
打开浏览器访问：`http://localhost:8000`

---

## 常用运维命令

### 启动/重启/停止
| 操作 | 命令 |
|------|------|
| 后台启动 | `docker-compose up -d` |
| 重启服务 | `docker-compose restart` |
| 停止服务 | `docker-compose stop` |
| 停止并删除容器 | `docker-compose down` |

### 查看日志
```bash
# 实时查看日志
docker-compose logs -f

# 查看最近100行日志
docker-compose logs --tail=100
```

### 查看运行状态
```bash
docker-compose ps
```

### 重新构建镜像（代码更新后）
```bash
docker-compose up -d --build
```

---

## 注意事项

1. **自动获取Cookie功能限制**：Docker容器内无法弹出浏览器窗口，建议手动获取Cookie后填入使用
2. **数据持久化**：CSV文件默认生成在项目根目录，可通过宿主机直接访问
3. **端口冲突**：若8000端口被占用，修改 `docker-compose.yml` 中 ports 映射

---

## 故障排查

- **镜像构建失败**：
  - pip安装包失败：Dockerfile已配置清华PyPI源加速
  - 如仍失败，可尝试清理镜像重新构建：`docker-compose build --no-cache`
- **容器无法启动**：执行 `docker-compose logs` 查看错误信息
- **页面无法访问**：检查端口映射和防火墙设置
- **爬虫失败**：确认Cookie有效性和网络连接正常
