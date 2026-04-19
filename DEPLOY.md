# B站评论爬虫系统 Docker 部署文档

## 环境要求

- macOS 系统
- Docker Desktop 已安装并运行

## 快速操作

### 启动项目

```bash
cd /Users/qidazhong/workspace/treatesting/bbcs
docker-compose up -d
```

### 停止项目

```bash
docker-compose down
```

### 重启项目

```bash
docker-compose restart
```

### 查看日志

```bash
docker-compose logs -f
```

### 查看运行状态

```bash
docker-compose ps
```

## 访问地址

- 服务地址：http://localhost:8000

## 文件说明

| 文件 | 说明 |
|------|------|
| Dockerfile | 构建镜像配置 |
| docker-compose.yml | 容器编排配置 |

## 注意事项

1. 首次启动会下载浏览器依赖，耗时较长
2. 端口 8000 需未被占用
3. 数据文件保存在项目根目录
