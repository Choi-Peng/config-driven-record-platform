# 配置驱动记录平台

一个基于 FastAPI + SQLite + Jinja2 的配置驱动型 Web 系统。

支持的核心能力：

- 账号登录、注册、登出与会话管理
- 角色权限控制（数据库 + 文件 + 本地资源规则）
- 多表单记录录入、查询、详情、编辑、删除
- 通用实体表动态管理（按配置生成管理页与 API）
- CSV/ZIP 导出
- YAML 配置驱动（主配置、表单配置、表配置）

## 快速开始

### 1) 安装依赖

推荐方式：

```bash
./deploy
```

或手动：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2) 配置入口

默认主配置入口为 `config/main.yaml`。
如需指定其他入口，可设置：

```bash
export APP_CONFIG_ENTRY=config/main.yaml
```
或在 .env 文件中设置：

```bash
APP_CONFIG_ENTRY=config/main.yaml
```

### 3) 初始化数据库

```bash
python init.py
```

### 4) 启动服务

```bash
./start
```

或：

```bash
python -m app.main
```

默认访问地址：`http://localhost:8000`

## 环境变量

- `APP_CONFIG_ENTRY`：主配置文件入口（默认 `config/main.yaml`）
- `ADMIN_USERNAME`：默认管理员用户名（默认 `admin`）
- `ADMIN_PASSWORD`：默认管理员密码（仅在第一次登录时有效）
- `SESSION_SECRET`：会话密钥（生产环境必须设置强随机值）

## 配置说明（概览）

主配置核心字段：

- `title` / `version`
- `data_path`
- `database`
- `form_pages`
- `active_form`
- `tables`
- `image_name_format`

说明：

- `form_pages.*.file` 指向表单配置文件
- `tables.*.file` 指向表配置文件
- 配置路径由 `ConfigManager` 按 `APP_CONFIG_ENTRY` 所在目录解析

[更多配置说明](docs/config_template_usage.md)

## 注意事项

- 未设置 `APP_CONFIG_ENTRY` 时，默认读取 `config/main.yaml`
- 初始化会删除现有数据库文件（含 `-wal`、`-shm`）
- 生产环境务必配置 `SESSION_SECRET` 与强密码


## License

This project is licensed under the MIT License.

---

> Powered by [Cursor](https://www.cursor.com/)