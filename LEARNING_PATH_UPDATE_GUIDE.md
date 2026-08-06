# 互动练习 GitHub 在线更新指南

## 一、运行方式

Android 只在线读取一个很小的 `learning-path-catalog.json`。课程题目、题图和音频按单元打成 ZIP，用户点击课程时才下载。下载完成后保存到 App 私有目录，后续离线使用。

```text
GitHub Release
├── learning-path-catalog.json
├── zh_beginner_unit_greetings-v2.zip
├── zh_beginner_unit_daily-v1.zip
└── zh_beginner_unit_travel-v1.zip

Android
├── files/learning/path/catalog.json
└── files/learning/packages/<package_id>/v<version>/
```

流程：

1. 进入学习路径，立即显示 APK 内置目录或手机缓存目录。
2. 后台读取 GitHub 最新目录。
3. 远程目录版本更高时刷新地图。
4. 未下载课程显示 `Download`，旧版本存在时显示 `Update`。
5. 点击后下载整个单元 ZIP，并同步显示该单元所有课程的进度。
6. 校验文件大小和 SHA-256，安全解压，再校验清单、课程 ID、题型和媒体。
7. 完整安装成功后才切换到新版本；失败时旧课程仍可继续使用。

## 二、源文件目录

```text
content/
├── learning_path/
│   └── catalog.json
└── packages/
    └── zh_beginner_unit_example/
        ├── manifest.json
        ├── lessons/
        │   ├── example_01.json
        │   └── example_02.json
        └── media/
            ├── example.webp
            └── example.mp3
```

`content/` 是编辑源文件。App 不直接读取这里；GitHub Actions 检查后生成 `dist/` 并创建 Release。

## 三、新增一道题

编辑对应的 `content/packages/<package_id>/lessons/<lesson>.json`，在 `exercises` 中新增对象。每道题的 `id` 必须在该课内永久唯一。

支持的题型：

- `single_choice`：单选题
- `listen_choice`：听力选择题，可用 `audio_text` 系统朗读或 `audio` 文件
- `true_false`：判断题
- `word_order`：拖动排序题
- `fill_blank`：填写题，必须提供 `pinyin`
- `matching`：配对题
- `dictation`：听写题，必须提供 `pinyin`，并提供 `audio_text` 或 `audio`
- `image_choice`：图片选择题

学习路径不发布 `pronunciation` 跟读题。新增客户端未实现的新题型必须先更新 APK。

修改题目后还要：

1. 把该单元 `manifest.json` 的 `version` 加 1。
2. 把目录中该单元所有课程的 `package_version` 改为同一新版本。
3. 把目录根部 `version` 和课程 `version` 提高。
4. 更新 `updated_at`，格式必须是 UTC：`2026-08-06T00:00:00Z`。
5. 运行新的 GitHub Release 版本。

## 四、新增一节课程

1. 在单元包的 `lessons/` 新建课程 JSON。
2. 在 `content/learning_path/catalog.json` 对应 `unit.lessons` 中新增节点。
3. `lesson.id` 必须等于课程 JSON 的 `lesson_id`。
4. `lesson_file` 必须指向该 JSON，例如 `lessons/travel_food.json`。
5. `exercise_count` 必须与 JSON 中实际题目数一致。
6. `required_lessons` 只能引用排在它前面的课程。
7. 按上一节说明提高包版本、目录版本并发布。

## 五、新增一个单元包

新建目录，例如：

```text
content/packages/zh_beginner_unit_food/
```

`manifest.json`：

```json
{
  "package_id": "zh_beginner_unit_food",
  "version": 1,
  "course_id": "zh_beginner",
  "unit_id": "unit_food"
}
```

然后在 `content/learning_path/catalog.json` 中新增 `unit_food`，所有课程统一引用：

```json
{
  "package_id": "zh_beginner_unit_food",
  "package_version": 1,
  "lesson_file": "lessons/food_order.json"
}
```

一个单元建议共用一个 ZIP，避免每道题产生一次网络请求。

## 六、题图和真人音频

图片放到包内 `media/`，选项引用相对路径：

```json
{
  "type": "image_choice",
  "options": [
    {"text": "你好", "value": "你好", "image": "media/hello.webp"},
    {"text": "再见", "value": "再见", "image": "media/goodbye.webp"}
  ],
  "answer": "你好"
}
```

音频示例：

```json
{
  "type": "listen_choice",
  "audio": "media/hello.mp3",
  "audio_text": "你好"
}
```

只有 `audio_text` 时 App 使用系统 TTS；提供 `audio` 时使用包内音频。不要写 GitHub 的绝对媒体地址，媒体与课程一起下载到本地。

## 七、发布

```text
GitHub 仓库 → Actions → Publish learning content → Run workflow
```

第一次使用 `1.3.0`；以后使用未占用的新版本，例如 `1.3.1`、`1.4.0`。Release 版本只是发布批次，单元包版本才决定 App 是否显示 `Update`。

工作流会严格检查：

- JSON、UTF-8、目录版本和时间格式
- 重复课程、单元、题目 ID
- 解锁依赖是否引用更早课程
- 目录题目数与实际题目数
- 选择答案、排序词块、配对数据
- 填写和听写拼音提示
- 图片和音频是否真实存在
- 包清单、课程 ID、单元 ID、版本是否一致
- ZIP 路径穿越、可执行文件、文件数和体积
- SHA-256、ZIP 完整性和稳定可重复构建

任何检查失败都不会发布错误 Release。

## 八、版本示例

只修改 `unit_travel` 的一道题：

```text
unit_travel manifest.version       1 → 2
unit_travel lessons package_version 1 → 2
catalog.version                    130 → 131
course.version                     130 → 131
updated_at                         改成当前 UTC 时间
GitHub Release                     1.3.0 → 1.3.1
```

其他单元包版本保持不变，用户只需要更新旅行单元。
