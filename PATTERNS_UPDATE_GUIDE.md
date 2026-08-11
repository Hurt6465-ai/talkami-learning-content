# 句型远程更新说明

## 目录职责

- `content/patterns/catalog.json`：只保存句型分类目录、每个分类包的版本/文件名/数量，以及 AI 提示词模板信息。
- `content/patterns/packs/*.json`：真正的 500 条句型数据，按 16 个大分类拆成 16 个文件。
- `content/patterns/prompts/pattern_analysis_v1.txt`：AI 教学提示词模板，不是句型数据。

发布后 GitHub Release 会生成：

- `patterns-catalog.json`
- 16 个 `pattern-*.json` 分类包
- `pattern-analysis-v1.txt`

Android 先读取 `patterns-catalog.json`。未下载分类显示 `Download`；点击后下载对应分类包，校验 SHA-256 后保存到：

`files/learning/patterns/<category_id>.json`

目录缓存保存到：

`files/learning/catalogs/patterns.json`

提示词缓存保存到：

`files/learning/prompts/pattern_analysis.txt`

## 更新一个分类

例如修改“比较句”：

1. 编辑 `content/patterns/packs/pattern_cat_09_v1.json`。
2. 把包内 `version` 从 1 升到 2。
3. 建议把 `content/patterns/catalog.json` 对应项的 `data_url` 改成新文件名，例如 `pattern-comparisons-v2.json`。
4. 把总目录 `version` 也升 1。
5. 更新 `updated_at`。
6. 运行 `Publish learning content` Action，使用新的 Release 版本。

`build_release.py` 会自动计算并写入 `data_sha256`、`item_count`、`data_version`。

## 更新 AI 教学提示词

`pattern-analysis-v1.txt` 就是统一的 AI 教学 Prompt 模板。

修改教学风格时，不需要改 500 条数据：

1. 新建 `content/patterns/prompts/pattern_analysis_v2.txt`。
2. 在 `content/patterns/catalog.json` 中把 `prompt_template.version` 升到 2。
3. 把 `prompt_template.url` 改为 `pattern-analysis-v2.txt`。
4. 把 `source_prompt` 改为对应 v2 源文件。
5. 总目录 `version` 也升 1，再发布新 Release。

## 稳定 ID

以下字段发布后尽量不要更改或重复使用：

- 分类 `id`，例如 `pattern_cat_09`
- 句型 `id`，例如 `pattern_347`
- `number`

以后做收藏、已学、最近学习时会依赖这些稳定 ID。
