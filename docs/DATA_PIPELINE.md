# 可追溯题库：离线校验与人工导入

本工具是 **Node 标准库离线 QA 工具**，不是爬虫，也没有自动验证面经真实性的能力。无需安装依赖、API 密钥或联网。当前快照日期上限固定为 `2026-10-25`；后续更新上限须同步评审。

## 校验与覆盖率

在项目根目录运行：

```sh
node scripts/data-pipeline.js
node scripts/data-pipeline.js --data data.json --answers answers.json --answers answers-extra.json
npm test
```

未显式指定答案时自动读取存在的 `answers.json` / `answers-extra.json`。输出 JSON 包含 `errors`、`warnings`、方向分布、来源/题目/去重事件数，以及答案 `answered`、`missing`、`orphaned`。有错误退出码为 1；缺答案与来源质量备注为警告/覆盖缺口，不伪装为已审核答案。`summary` 非空只表示有答案草稿，不代表技术正确或已审核。

校验：必填字段、七方向标签、唯一来源/问题 ID、HTTP(S) URL、同一规范 URL 重复、稳定的来源引用与公司一致性、去重事件跨公司冲突（明确标为同一 source 的 `eventUnit: "source_document"` 合集除外）、重复记录、真实且不晚于上限的完整日期、孤立答案 ID。来源 URL 去除 fragment、`utm_*`、`spm`、`from` 跟踪参数并排序参数，仅用于重复发现，**不会修改原始 URL**。未知年份使用 `null`，不得以收录日期代替面试年份。`verifiedAt` 是资料检查日期，不是面试时间。

`qualification: "index-only"` 的索引页面不能支撑活跃题目记录。其他证据等级需要人工审核，不能靠字符串或校验通过推断可信。

## 安全添加人工采集数据

准备 JSON：`{"sources": [...新增完整来源...], "questions": [...新增完整题卡...]}`。字段与 `data.json` 相同；即使没有新增来源，也需提供 `sources: []`。新增题卡可以引用已有来源。不可复用已有 ID 来覆盖旧内容。

```sh
# 默认只预览合并后的校验和覆盖报告；不会修改任何数据
node scripts/data-pipeline.js --import candidates.json
# 人工审阅记录和原文后，才明确落盘
node scripts/data-pipeline.js --import candidates.json --write
```

只有无错误才写入；原数据备份到 `data.json.bak`，通过临时文件替换写入。已有 `.bak` 会阻止覆盖，应先人工归档备份。检测到原数据变化也会拒绝写入。候选文件不含可信执行指令，永远只解析 JSON。

此导入器 **只追加、不自动归并**，不自动修改已有题目记录；往旧题卡补来源需人工编辑并再次校验。同一面试帖子、转载与合集应按真实独立事件复用 `event`，不可按段落拆分增加次数。词面相似不等于相同考点；人工合并时须保留原问法与 `mergeReason`。工具无法判定两个不同 URL 是否转载，也不能独立验证公司归属、原作者、时间或所谓“高频”。只显示去重来源事件数，不生成面试频率。

## 运行文件构建

```sh
node scripts/data-pipeline.js && node scripts/build.js
```

`_site/` 每次重建，只收录 `index.html`、`style.css`、`app.js`、`core.js`、`data.json`、`taxonomy.json` 以及存在的两个答案覆盖文件。备份、候选数据、测试、私人笔记和 QA 截图不进入部署目录。GitHub Pages workflow 已串联 `npm test`、数据校验、构建；本地运行这些命令不会发布网站。

多公司合集需在来源上显式提供 `companies` 数组，逐条记录公司必须属于该数组；不可通过拆分含糊的公司展示字符串自动猜测。
