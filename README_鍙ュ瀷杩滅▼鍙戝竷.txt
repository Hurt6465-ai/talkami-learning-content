句型远程数据已经改为“目录 + 分类包”结构，和单词/短句的远程包思路一致。

pattern-analysis-v1.txt = AI 教学提示词模板，不是 500 条句型数据。

源文件：
content/patterns/catalog.json                  只做分类目录
content/patterns/packs/pattern_cat_01_v1.json  基础陈述与判断
...
content/patterns/packs/pattern_cat_16_v1.json  存现与特殊结构
content/patterns/prompts/pattern_analysis_v1.txt AI Prompt

Release：
patterns-catalog.json
16 个 pattern-*.json
pattern-analysis-v1.txt

Android：
目录自动更新并缓存；每个分类未下载时显示 Download，点击下载对应分类包到手机。
