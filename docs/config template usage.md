---
title: 配置模板使用说明
version: 1.1
---

# 配置模板使用手册

`config-template/` 目录提供了系统配置的标准模板。

## 1. 主配置：`main.yaml`

主配置用于定义系统基础信息、数据路径、数据库参数、表单页面入口和数据表入口。

关键字段说明：

- `title`：系统名称
- `version`：配置版本
- `data_path`：数据根目录及数据库/文件/图片路径
- `database`：SQLite 相关参数（如 `journal_mode`、`synchronous`）
- `form_pages`：表单页面清单（页面键 -> 标题 + 文件路径）
- `active_form`：默认打开的表单页面键
- `tables`：数据表清单（表键 -> 标题 + 文件路径）
- `image_name_format`：上传图片命名格式（支持系统变量与表单字段变量）

示例：

[main.yaml示例](../config.bak/main.yaml)

## 2. 公共字段模板：`forms/common.yaml`

此文件用于统一定义字段结构，避免在每个表单中重复编写。

- `field_templates`：字段模板（定义通用属性，如 [`type`](#5-字段类型)、`required`、`width`、`db_type`）
- `common_fields`：公共字段（基于字段模板生成，可按需覆盖属性）

该模板大量使用 YAML 锚点（`&name`）和引用（`*name`）：

- `&xxx` 定义锚点
- `*xxx` 引用锚点
- `<<: *xxx` 合并锚点内容后再覆盖字段

示例：

[common.yaml示例](../config.bak/forms/common.yaml)

## 3. 表单页面配置：`forms/form.yaml`

单个表单页面由 `version`、`title`、`icon`、`groups` 组成，支持通过 `!include` 引入公共字段。

关键点：

- `common_fields: !include: common.yaml`：引入公共字段配置
- `groups`：表单分组，每个分组包含 `title`、`icon`、`fields`
- `combine_datetime`：是否将 `record_date + record_time` 合并显示为一个日期时间输入框
- `fields` 支持三种写法：
  - 直接复用公共字段：`- *crop_name`
  - 复用公共字段并覆盖：`- <<: *amount`
  - 直接基于字段模板创建新字段：`- <<: *text_base`

`source.depends_on`（或字段级 `depends_on`）可用于级联下拉，子字段选项会随父字段变化。

示例：

[form.yaml示例1](../config.bak/forms/greenhouse.yaml)
[form.yaml示例2](../config.bak/forms/open_field.yaml)

## 4. 数据表配置：`tables/table.yaml`

表配置用于定义数据库建表信息、初始数据和前端展示规则。

关键字段：

- `db_info.table_name`：数据库表名
- `db_info.columns`：字段名与类型
- `db_info.foreign_keys`：外键关系（`表.字段`）
- `db_info.indexes`：索引
- `db_info.triggers`：触发器 SQL
- `seed_data`：初始化数据
- `editable_columns`：允许编辑的列
- `show_columns`：前端展示列
- `column_labels`：列表页/新建页列名别称映射（例如 `name: 名称`）
- `column_mapping`：关联字段映射（例如 `role_name: role_id#roles.name`）

`db_info`各字段使用SQL语法描述。

示例：

[table.yaml示例](../config.bak/tables/crops.yaml)

## 5. form表单字段类型

form表单字段类型与数据库字段类型一一对应。

- `text`：文本
- `number`：数字
- `date`：日期
- `time`：时间
- `select`：下拉框
- `radio`：单选框
- `checkbox`：复选框
- `textarea`：文本框
- `image`：图片

### `select`、`radio`、`checkbox`

`select`、`radio`、`checkbox` 需要指定 `source` 来源。

`source` 需包含 `type` 和 `values` 字段。

- `type`：来源类型 (options/database)
- `values`：来源数据
  - 若 `type` 为 `options`，则 `values` 为静态选项列表
  - 若 `type` 为 `database`，则 `values` 为数据库表名和键名
    - `table`：数据库表名
    - `key`: 键名
  - `depends_on`：依赖字段，依赖字段发生变化时，更新选项（建议放在 `source` 下）

示例：

```yaml
# select options示例
- <<: *select_field
  key: option_mode
  label: 选项名称
  source:
    type: options
    values: [选项1, 选项2, 选项3]
    depends_on: previous_option

# select database示例
- <<: *select_field
  key: database_mode
  label: 选项名称
  source:
    type: database
    values:
      table: database_table
      key: name
```

### `image`

`image` 需要指定 `accept` 和 `multiple` 字段。

- `accept`：图片格式
- `multiple`：是否多选, 默认true

示例：

```yaml
- <<: *image_field
  key: images
  label: 现场照片
  accept: image/*
  multiple: true
```

上传后的图片会保存在 `data_path.images/<form_page_title>/` 指定目录下。
系统会自动创建目录，其中 `<form_page_title>` 来源于当前表单页面标题（会做安全化处理）。

可在 `main.yaml` 中配置 `image_name_format` 来修改图片名称格式。

### 5.1 图片命名格式（`image_name_format`）

默认命名格式：

```yaml
image_name_format: "{timestamp}_{image_index}"
```

> 注：如果命名格式中未显式写后缀，系统会自动使用上传文件原始后缀（如 `.jpg`、`.png`）。
>
> 默认保存路径示例：`data/images/温室环境/20260423120000_1.jpg`

**系统变量：**
- `{form_page_key}`：表单页面键
- `{form_page_title}`：表单页面标题
- `{table_key}`：记录表键（如 `records_open_field`）
- `{table_title}`：记录表标题（与表单标题一致）
- `{timestamp}`：时间戳
- `{image_index}`：图片索引，从1开始
- `{field_key}`：当前图片字段键（如 `images`）

**表单字段变量（推荐）：**

可直接使用单花括号引用任意字段键（值来自当前提交记录）：

```yaml
image_name_format: "{form_page_title}_{timestamp}_{field_1}_{field_2}_{field_3}_{field_4}_{image_index}"
```

如果某个字段不存在或为空，替换结果为空字符串。

示例：
```yaml
# 表单中存在字段 recorder=张三
image_name_format: "{form_page_key}_{timestamp}_{recorder}_{image_index}"
# 保存后示例路径：data/images/露地环境/open_field_20260423120000_张三_1.jpg
```

### 5.2 记录详情页图片更新行为

- 进入记录详情页点击“更新”后，可新增/删除现场照片
- 保存时会同时更新普通字段与图片字段
- 被删除的旧图片会从磁盘清理（仅 `/images/...` 映射文件）

## 6. 额外建议

- 字段键命名建议保持稳定，避免历史数据出现多套别名
- `show_columns` 使用表单实际字段键，避免展示与存储字段不一致
- 需要更友好的列名时，请在表配置中使用 `column_labels`
