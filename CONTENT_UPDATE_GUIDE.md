# 后续新增内容操作清单

## A. 在已有单词包里加单词

1. 复制当前词包为新版本文件，例如 `travel_words_v1.json` 复制为 `travel_words_v2.json`。
2. 在 `items` 中追加新单词。
3. 新单词使用新的唯一 `id`，不要改旧单词 ID。
4. 把词包根部 `version` 从 1 改为 2。
5. 在 `content/words/catalog.json` 对应项中修改：
   - `data_url`
   - `data_version`
   - `source_data`
   - `badge` 和 `subtitle` 中显示的数量
6. 运行 Actions，输入新的 Release 版本。

## B. 新增整个单词分类

1. 新建 `content/words/packs/<分类>_v1.json`。
2. 新建 `content/words/covers/<分类>_v1.webp`。
3. 在 `content/words/catalog.json` 的 `items` 中新增分类。
4. 保证目录 `level` 等于词包 `categoryId`。
5. 运行 Actions。

## C. 在已有口语包里加短句

1. 复制当前短句包为新版本文件。
2. 追加短句，并为每句设置稳定唯一的 `id`。
3. 提高短句包根部 `version`。
4. 修改 `content/speaking/catalog.json` 对应叶子节点的：
   - `data_url`
   - `data_version`
   - `source_data`
   - `badge` 和 `subtitle`
5. 运行 Actions。

## D. 新增整个口语包

1. 新建 `content/speaking/packs/<口语包>_v1.json`。
2. 在 `content/speaking/catalog.json` 的合适分组 `children` 中新增叶子节点。
3. 保证目录叶子节点 `id` 等于短句包 `pack_id`。
4. 运行 Actions。

## E. 发布检查

发布前确认：

- 所有 JSON 可以解析
- 新文件已经上传
- 文件路径大小写完全一致
- 数据包版本已增加
- Release 版本从未使用过
- 最新 Release 中包含 `words-catalog.json` 和 `speaking-catalog.json`

本版本建议发布为：`1.1.0`
