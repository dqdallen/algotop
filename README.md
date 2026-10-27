# AlgoWen · 算问集（v8）

可追溯的算法面经复习静态站，以及**独立、私有、仅本机**的候选审核工具。品牌由 AlgoTop 更新为 AlgoWen；兼容保留既有数据 ID、学习记录键和 `ALGOTOP_*` 环境变量。基线仍为 323 题，ID 保留；两处题干有来源证据支持的更正，详见真实材料验收说明。演示、模型建议或待审核候选不会增加正式题卡。

## 先运行复习网站（不需要密钥）

需要 Node.js 与 Python 3；当前验证环境为 Node 24、Python 3.12。站点无 npm 第三方依赖。

```sh
npm test
node scripts/data-pipeline.js
node scripts/build.js
python3 -m http.server 8766 --bind 127.0.0.1 --directory _site
```

在同一台电脑打开 **http://127.0.0.1:8766/**。不要双击 HTML，也不要直接把项目根目录当作公开目录；构建只将运行文件白名单复制到 `_site/`。此命令不是公网部署。

## 本地采集 / 审核控制台

先阅读 [USER-ACCEPTANCE.md](USER-ACCEPTANCE.md)：包括无需密钥的免费沙盒闭环、真实模型的可选配置、明确预期结果和需要你亲自验收的边界。

```sh
python3 tools/local_console.py --port 8765
```

只访问 **http://127.0.0.1:8765**。审核要求 Node 在 PATH 中；文件锁依赖 POSIX，请用 macOS/Linux/WSL，不使用原生 Windows Python。可选 OpenAI SDK/HTML 解析器见验收文档；缺少它们仍可免费演示或使用内置 HTML 回退。

工作流：合法来源获取或手动导入 → 核对规范化正文 → 逐次确认提供方内容传输（演示不调用 API）→ 候选默认待定 → 逐题新增/合并/排除 → 差异预览 → 显式确认写入本地副本 → 哈希保护的最后事务回滚。它不写 GitHub、不发布、不自动增加正式题库。

- 根 `data.json` 只读；真实工作副本位于私有 `.local-review/`。演示使用独立临时沙盒。
- 新文档/重新提取使旧入库预览失效；重复提交安全重放，不重复入库。
- 完整原文不写入审计日志，但短证据、候选、预览和事务仍可能敏感。清空会话不删除持久记录和下载。
- 更多事务/CLI 用法：[本地审核说明](LOCAL-CONSOLE-V7.md)、[审核工具说明](tools/collection/README-REVIEW-V7.md)。这些历史文档中的 v7/AlgoTop 名称指兼容基础版本；当前设置/验收以本文与 USER-ACCEPTANCE 为准。

## 数据与学习记录如何理解

- 综合题是复习卡，不表示所有关联来源都逐字问过每个子问题；原始问法为改述并附出处。
- 来源是作者自述或汇编，不代表公司认证。来源提及数不是独立面试次数、真实考频或通过率；重复来源与多轮合集不能虚增计数。
- 公司、招聘岗位和学习主题分开；不能因为问 LoRA 就推断大模型岗。公司/岗位/日期筛选必须在同一条记录匹配。
- 来源发布日期、面试日期、采集日期不同；未知日期、公司、岗位不猜测。题库不是全网穷尽样本，也不能按品牌更新日认定内容都是新题。
- 参考答案是另行编写的学习材料，不是原作者/公司标准答案；仍需专业人工复核。
- 学习笔记、收藏、掌握状态只保存在当前浏览器，可导出备份；无账号同步。清除站点数据或更换域名/端口可能使旧记录不可见，迁移前先导出。

运行数据：`data.json`、`taxonomy.json`、`answers.json`、`answers-extra.json`。离线校验与构建在 `scripts/`；私有采集/审核工具在 `tools/collection/`。

## 本地验证

```sh
npm test
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest discover -s tools/collection -p 'test_*.py'
node --check local-console/app.js
node scripts/data-pipeline.js
node scripts/build.js
```

离线测试、人工模拟和浏览器检查不等同于真实提供方鉴权、模型质量、账单或 GitHub 部署验证。可选依赖缺失时相关离线集成测试会明确 skip；另外 3 项私有来源回放测试在没有显式提供私有材料目录时 skip。这两种原因不同，不要将 skip 当作成功执行。详见 [真实材料验收说明](tools/collection/README-REAL-ACCEPTANCE-V8.md) 与 [改名/迁移说明](RENAME-V8.md)。

## 发布与定时任务边界

只公开 `_site/` 构建白名单，不公开整仓目录、原文、私有候选、审核日志、下载备份或密钥。代码中 `.github/workflows` 的实际存在和远端 Actions 成功结果才是部署证据；本文不声称本地新功能已上线。

`tools/collection/workflow-drafts/weekly-candidates.yml.disabled` 是不生效的私有采集草案，不是已开启的 cron。启用前需要另行确认私有仓库/受保护环境、Secrets、来源/正文权限、内容传输、费用限制与 artifact 保留策略；不要直接将草案移入工作流目录。公开复习站和私有采集任务应分离。

本说明替代旧 AlgoTop README 中不再随本快照提供的 `docs/` 链接与过期的部署准备状态；不构成来源授权或上线声明。
