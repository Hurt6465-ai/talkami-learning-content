# Talkami Learning Content 远程内容仓库

这个仓库用于给唐僧叨叨二开的学习模块发布：

- 单词目录与单词包
- 口语短句目录与短句包
- 学习路径目录与课程 ZIP

Android 不会每次在线读取每个单词或每张图片。它先读取小目录，发现版本变化后下载数据到本地缓存，离线时继续使用缓存或 APK 内置内容。

## 发布一次新内容

1. 修改 `content/` 中的源文件。
2. 打开 GitHub 仓库的 `Actions`。
3. 运行 `Publish learning content`。
4. 输入一个从未使用过的新版本，例如 `1.0.1`。
5. 工作流会检查 JSON、计算 SHA-256，并把 `dist/` 中的文件发布到新的 Release。

## 单词

目录：`content/words/catalog.json`

词包：`content/words/packs/*.json`

新增一个单词包时，在目录里增加一项，并提供：

- 唯一 `id`
- `target: "word"`
- `level`，必须等于词包内的 `categoryId`
- `data_url`
- `data_version`
- `source_data`
- 可选封面 `source_cover` 与 `cover_url`

修改已有词包时：

- 提高词包根部的 `version`
- 最好换新文件名，例如 `travel-v2.json`
- 同步修改目录的 `data_url`

脚本会自动填写 `data_sha256` 和 `item_count`。

## 口语短句

目录：`content/speaking/catalog.json`

短句包：`content/speaking/packs/*.json`

新增一个口语分类时，在目录的 `items` 或 `children` 中增加叶子节点，并提供：

- 唯一 `id`
- `target: "study"`
- `data_url`
- `data_version`
- `source_data`
- 可选 `asset`，用于指定 APK 内置离线兜底；纯远程分类可留空

短句包根部至少包含：

```json
{
  "pack_id": "speak_travel",
  "title": "旅行问路",
  "version": 1,
  "phrases": []
}
```

其中 `pack_id` 必须和目录叶子节点的 `id` 一致。脚本会自动填写 `data_sha256` 和 `item_count`。

## Android 地址

Android 项目的：

`wklearning/src/main/assets/learning/config/remote_content.json`

已经配置为：

`https://github.com/Hurt6465-ai/talkami-learning-content/releases/latest/download/`

并读取：

- `words-catalog.json`
- `speaking-catalog.json`
- `learning-path-catalog.json`

## Release 生成文件

当前示例会生成：

- `words-catalog.json`
- `hsk1-demo-v1.json`
- `hsk1-demo-cover-v1.webp`
- `speaking-catalog.json`
- `speak-remote-demo-v1.json`
- `learning-path-catalog.json`
- 课程 ZIP
- `content-metadata.json`

仓库需要保持 Public。不要把 GitHub 私人 Token 写入 APK。
