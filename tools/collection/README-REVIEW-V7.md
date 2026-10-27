# V7 本地审核入库事务（不发布）

`review_commit.py` 将 V6 候选 JSON 与**独立的人类决定**组合成预览，再显式确认写入隔离工作副本。不会修改传入 baseline、公开 `_site`、答案覆盖文件或浏览器学习笔记，也不会调用 API、抓取、启用定时任务或部署。

## 决定文件

每个候选必须有且只有一个决定；未知字段、重复 ID、自称批准的候选、非通用题、错配来源、未确认的决定均拒绝。

```json
{
  "schema_version": 1,
  "reviewer": "本地审核人",
  "decisions": [
    {"candidate_id": "候选ID", "action": "add", "common_question": true, "source_reviewed": true},
    {"candidate_id": "另一个候选ID", "action": "merge", "target_question_id": "q001", "common_question": true, "source_reviewed": true},
    {"candidate_id": "排除候选ID", "action": "exclude", "reason": "个人项目实现，不属于通用题"}
  ]
}
```

`common_question` 与 `source_reviewed` 是审核人实际检查后的独立确认，不可由抽取模型自动填写。候选中的批准标记不能代替它们。合并目标必须是现有稳定 ID；名称精确重复的新增需改为合并，歧义不会自动猜测。

## CLI

在项目根目录运行。需要 Python 3.10+ 与 Node.js 18+（Node 用于复用完整题库 schema audit；其余为 Python 标准库）。启动控制台/CLI 的同一个终端中先检查 `python --version` 与 `node --version`，确保 Node 安装目录在 `PATH` 中；从桌面启动时可能与终端的 PATH 不同，可在已确认这两个命令可用的终端启动。没有 Node 时事务会以 `schema_validator_unavailable` 拒绝，不会跳过校验。现有仅产生候选的 workflow 不负责应用审核决定；未来若独立运行 review_commit，必须先配置 Node。此版本不启用或修改定时运行。

```sh
python tools/collection/review_commit.py --workspace /tmp/algotop-private-review preview candidates.json --decisions decisions.json
# dry-run 是 preview 的同义词，均不改变工作副本题库内容。
python tools/collection/review_commit.py --workspace /tmp/algotop-private-review apply <preview_id> --confirm
python tools/collection/review_commit.py --workspace /tmp/algotop-private-review state
python tools/collection/review_commit.py --workspace /tmp/algotop-private-review rollback <transaction_id> --confirm
```

首次访问工作区只复制 baseline。`--baseline` 可指定参考题库；不得与工作区 data.json 相同。演示候选在普通工作区不可提交；只有显式 `--demo-sandbox` 创建的隔离沙盒可应用。模式写入工作区标记，不能事后切换。控制台固定使用本地沙盒，演示内容不会进入真实参考题库。

## 证据与计数

- 预览分别给出新增题、新增唯一来源、新增「题 × 来源」关系、附加证据、私有排除数；另列入库前后题目数、唯一来源数、题–来源组数、记录条数与审核证据片段数。旧数据原有记录与新增审核片段分别计量，不假称历史证据已重新逐条核验；这些均不是面试场次/人数。
- GitHub 的 www、raw、blob 不同文件归并为同一仓库身份。重复来源只补证据，不增加来源数。
- 新题使用确定性的稳定 ID，空答案及「待专业审核」状态；既有 ID、别名、答案及所有其他字段原样保留。
- 新来源公司、岗位、面试日期保持未知；候选日期仅保留为声明，不提升为已核验日期，也不按题目反推岗位。
- 保留短证据、定位符、来源 URL、原候选 ID、抽取 hash/模型/解析器等 provenance。已有证据不会被改写。
- 控制台将当前来源正文**在内存中**传给 `preview(..., trusted_document=...)`，核对正文 SHA、来源身份、Unicode 字符偏移及原文短引文。审计只保存 hash 和核对结果，不保存全文。
- 离线导出的 JSON 没有原始全文，无法独立重新验证引文。此时要求审核人 `source_reviewed: true`，标注 `human_attested_not_independently_verified`；不是自动真实性背书。没有足够证据请排除或留待审核，不要勾选确认。

## 事务与恢复

预览 ID 绑定当前字节 SHA、候选、决定、来源核对状态及结果 SHA。应用时重新计算完整变更并通过现有 `scripts/data-pipeline.js` 全量 schema 验证；过期预览拒绝。使用工作区进程锁，写前再次检查 SHA。

唯一产品数据文件为工作区 `data.json`，通过同目录临时文件、fsync、原子替换写入；不做多产品文件事务。先持久化 `.review/transactions/<id>/before.bin` 原始字节备份与 prepared manifest，再替换 data.json，最后标记 applied。中断后重复 apply 可按 SHA 恢复；重复提交相同预览不重复入库。已回滚预览不能重新应用。

回滚仅允许最新未回滚事务，且当前 SHA 必须等于该事务结果 SHA；中途编辑绝不覆盖。先写 rolling_back 日志，再恢复备份原始字节；中断后重试可完成日志恢复。备份 SHA 不匹配则拒绝。审核目录和备份为私有工作资料，不应公开打包；manifest 记录决定、题/来源 ID、差异计数和时间，不存文章全文。

锁协调本工具的并发调用；不要由其他编辑器同时写同一个工作区文件。任何本地磁盘故障/外部改动都应检查 journal 与 SHA，勿删除备份来强行继续。

## 验证

```sh
python -m unittest discover -s tools/collection -v
python -m unittest discover -s tests -p 'test_*.py' -v
npm test
```

专用事务测试覆盖 dry-run、显式确认、稳定 ID/字段保留、仓库去重、证据补充、排除私有化、演示隔离、来源核对、畸形结构、过期预览、重复提交、回滚冲突及中断恢复。所有写入使用临时测试沙盒。
