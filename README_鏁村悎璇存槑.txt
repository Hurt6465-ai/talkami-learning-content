GitHub 内容仓库整合补丁：句型分包 + 学习首页 Hero

覆盖到 talkami-learning-content 仓库根目录。
此包将：
- 保留 16 个句型分类包、500 条句型、pattern_analysis_v1.txt
- 增加 content/home/catalog.json 与 Hero WebP
- 使用较新的 build_release.py，同时构建 patterns 与 learning-home
- remote_content.json 统一从 GitHub Releases/latest/download 获取 words/speaking/patterns/home 等资源

源文件请改 content/；dist/ 是发布产物，不要手工维护。
