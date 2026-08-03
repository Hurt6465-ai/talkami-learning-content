# Talkami Learning Content 示例仓库

这是针对当前唐僧叨叨二开学习模块远程内容格式制作的最小示例。

## 首次使用

1. 在 GitHub 新建公开仓库：`talkami-learning-content`。
2. 将本目录所有文件上传到仓库根目录。
3. 打开仓库 `Actions`，运行 `Publish learning content`。
4. 输入版本 `1.0.0`，点击运行。
5. Actions 会校验 JSON、打包课程、计算 SHA-256，并建立 Release。
6. 将根目录 `remote_content.json` 中的 `REPLACE_WITH_GITHUB_USERNAME` 改成你的 GitHub 用户名。
7. 用它覆盖 Android 项目的：
   `wklearning/src/main/assets/learning/config/remote_content.json`
8. 重新打包安装一次。此后修改单词和课程，只需发布新内容，不需要重新安装 App。

## 每次更新

- 修改 `content/` 中的 JSON 或 WebP。
- 单词包更新时提高 `version`、`data_version` 和 `cover_version`。
- 课程目录更新时提高根级 `version` 和 `updated_at`。
- 课程包内容更新时提高包 `manifest.json` 的 `version`，并同步提高目录中每节课的 `package_version`。
- 提交后再次运行 Actions，例如输入 `1.0.1`。

## Release 最终会生成

- `words-catalog.json`
- `hsk1-demo-v1.json`
- `hsk1-demo-cover-v1.webp`
- `learning-path-catalog.json`
- `zh_beginner_unit_greetings-v1.zip`
- `content-metadata.json`

不要把源仓库设置成私有后让 App 直接下载，因为私有 Release 需要 GitHub Token，而 Token 不能写进 APK。
