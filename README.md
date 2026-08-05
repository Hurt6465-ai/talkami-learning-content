# Talkami Learning Content 远程内容仓库

这个仓库用于给唐僧叨叨二开的学习模块发布：

- 单词目录、单词包和单词封面
- 口语短句目录和短句包
- 学习路径目录和课程 ZIP

App 的正常流程是：

1. 在线读取很小的目录 JSON。
2. 目录发现新分类或更高的数据版本。
3. 用户打开对应分类时，App 下载数据包。
4. 数据通过 SHA-256 校验后保存到手机本地。
5. 之后从本地读取；断网时继续使用缓存或 APK 内置内容。

## 当前内容

### 单词：75 个

- HSK 1 基础词汇：30 个，数据版本 2
- 旅行出行：15 个
- 餐饮美食：15 个
- 工作办公：15 个

每个单词包都包含中文、拼音、缅语释义、英文释义、例句、例句拼音和缅语例句。

### 口语：81 句

- 日常交流：15 句
- 旅行问路：20 句，数据版本 2
- 酒店入住：12 句
- 餐厅点餐：12 句
- 购物付款：12 句
- 紧急求助：10 句

## 发布新内容

1. 修改 `content/` 中的源文件。
2. 打开 GitHub 仓库的 `Actions`。
3. 运行 `Publish learning content`。
4. 输入一个从未使用过的新 Release 版本，例如 `1.1.0`。
5. 工作流会：
   - 检查 JSON 格式
   - 检查重复 ID
   - 检查目录和数据包 ID 是否一致
   - 检查必填中文、拼音和缅语释义
   - 计算 SHA-256
   - 统计单词或短句数量
   - 生成完整 `dist/`
   - 发布新的 GitHub Release

每个最新 Release 都会包含全部当前资源，不是只包含本次改动，因此 `/releases/latest/download/` 下的所有地址都能继续使用。

## 单词维护

目录：

`content/words/catalog.json`

数据包：

`content/words/packs/*.json`

封面：

`content/words/covers/*.webp`

修改已有单词包时：

- 保持目录 `id` 和词包 `categoryId` 不变
- 保持已有单词 `id` 不变
- 提高词包根部 `version`
- 换一个带新版本的文件名
- 同步修改目录中的 `data_url`、`data_version` 和 `source_data`
- 只改封面时提高 `cover_version`，并修改 `cover_url` 与 `source_cover`

新增整个单词分类时：

- 新建一个词包 JSON
- 新建一张 WebP 封面
- 在 `content/words/catalog.json` 中新增一个叶子节点
- 目录 `level` 必须等于词包 `categoryId`

脚本会自动填写最终目录中的 `data_sha256` 和 `item_count`。

## 口语维护

目录：

`content/speaking/catalog.json`

短句包：

`content/speaking/packs/*.json`

修改已有口语包时：

- 保持目录叶子节点 `id` 和短句包 `pack_id` 不变
- 保持已有短句 `id` 不变
- 提高短句包 `version`
- 换一个带新版本的文件名
- 同步修改目录中的 `data_url`、`data_version` 和 `source_data`

新增口语包时：

- 新建一个短句包 JSON
- 在 `content/speaking/catalog.json` 的相应 `children` 中新增叶子节点
- 目录叶子节点 `id` 必须等于短句包 `pack_id`

当前口语卡片不使用远程封面，所以无需上传口语封面。

## Android 地址

Android 项目的：

`wklearning/src/main/assets/learning/config/remote_content.json`

应配置为：

`https://github.com/Hurt6465-ai/talkami-learning-content/releases/latest/download/`

并读取：

- `words-catalog.json`
- `speaking-catalog.json`
- `learning-path-catalog.json`

仓库必须保持 Public。不要把 GitHub 私人 Token 写入 APK。

## 重要版本规则

有三类版本：

- GitHub Release 版本：每次运行 Actions 输入新值，例如 `1.1.0`
- 数据包版本：只有修改对应单词包或口语包时才增加
- 封面版本：只有更换单词封面时才增加

不要复用旧 Release 版本，也不要修改已有内容的稳定 ID。
